"""
Worker para processamento em background.
Gerencia jobs de scan, organização, análise IA e detecção facial.
"""
import os
import logging
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.config import settings
from app.models import Media, ProcessingJob, Face, media_faces
from app.services.organizer import scan_source_directory, scan_library_directories, organize_file, cleanup_source_trash, get_media_type, get_media_date, get_image_dimensions, get_video_metadata
from app.services.duplicates import update_perceptual_hash, check_duplicate, compute_perceptual_hash
from app.services.ai_vision import process_media_ai
from app.services.face_recognition_service import process_faces_in_media, cluster_unknown_faces
from app.services.file_ops import media_file_operation_lock
from app.services.organizer import compute_sha256

logger = logging.getLogger(__name__)


class StorageUnavailableError(RuntimeError):
    """Levantada quando um ou mais diretórios críticos estão indisponíveis."""
    def __init__(self, unavailable: list[str]):
        self.unavailable = unavailable
        super().__init__(
            f"Diretórios indisponíveis: {', '.join(unavailable)}. "
            "Operação cancelada para proteger o banco de dados."
        )


def _require_storage():
    """
    Verifica se todos os diretórios críticos estão acessíveis.
    Lança StorageUnavailableError se algum estiver indisponível.
    Deve ser chamada no início de qualquer job que toca arquivos.
    """
    from app.services.mount_checker import all_critical_dirs_available
    ok, missing = all_critical_dirs_available()
    if not ok:
        raise StorageUnavailableError(missing)


def safe_commit(db: Session, context: str = "") -> bool:
    """Attempt to commit the session; rollback on failure and log error."""
    try:
        db.commit()
        return True
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.error(f"DB commit failed during {context}: {e}")
        return False


def _create_job(job_type: str):
    """Cria um registro de job em background."""
    db = SessionLocal()
    try:
        job = ProcessingJob(
            job_type=job_type,
            status="running",
            started_at=datetime.datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id
    finally:
        db.close()


def _update_job(job_id: int, status: str, processed_items: int = None, total_items: int = None, error_message: str = None):
    db = SessionLocal()
    try:
        job = db.query(ProcessingJob).get(job_id)
        if not job:
            return
        job.status = status
        if processed_items is not None:
            job.processed_items = processed_items
        if total_items is not None:
            job.total_items = total_items
        if error_message is not None:
            job.error_message = error_message
        if status in ("completed", "failed"):
            job.completed_at = datetime.datetime.utcnow()
        db.commit()
    finally:
        db.close()


def run_rclone_download_job() -> dict:
    """Job: baixa remotes configurados via rclone para o source_dir.

    Deduplica pré-download por nome de arquivo (consultando o banco) e deixa o
    scan/organizador organizar e deduplicar por SHA256 o que foi baixado.
    """
    _require_storage()
    from app.services.rclone_sync import run_rclone_download

    job_id = _create_job("rclone_download")

    def _on_progress(done: int, total: int, last_line: str):
        # Atualiza o job a cada pasta concluída / linha de status do rclone,
        # permitindo acompanhar o andamento na web (barra de progresso).
        _update_job(job_id, "running", processed_items=done, total_items=total)

    try:
        with media_file_operation_lock:
            result = run_rclone_download(on_progress=_on_progress)
        _update_job(
            job_id,
            "completed",
            processed_items=result.get("folders", 0),
            total_items=result.get("total_folders", result.get("folders", 0)),
        )
        logger.info(f"[rclone] concluído: {result}")
        return result
    except Exception as e:
        _update_job(job_id, "failed", error_message=str(e))
        logger.error(f"[rclone] job falhou: {e}")
        raise


def _preprocess_library_file(filepath: str) -> dict:
    """
    Pré-processa um arquivo de biblioteca em paralelo (sem acesso ao DB).
    Extrai SHA256, metadados e perceptual hash.
    """
    try:
        file_hash = compute_sha256(filepath)
        filename = os.path.basename(filepath)
        media_type = get_media_type(filepath)
        media_date = get_media_date(filepath)
        date_file = datetime.datetime.fromtimestamp(os.path.getmtime(filepath))

        width, height, duration = None, None, None
        video_codec = None
        needs_transcode = False
        phash = None

        if media_type == "image":
            width, height = get_image_dimensions(filepath)
            phash = compute_perceptual_hash(filepath)
        elif media_type == "video":
            meta = get_video_metadata(filepath)
            width, height = meta.get("width"), meta.get("height")
            duration = meta.get("duration")
            video_codec = meta.get("codec")
            web_codecs = {"h264", "hevc", "vp8", "vp9", "av1"}
            if video_codec and video_codec not in web_codecs:
                needs_transcode = True

        return {
            "filepath": filepath,
            "filename": filename,
            "file_hash": file_hash,
            "media_type": media_type,
            "media_date": media_date,
            "date_file": date_file,
            "width": width,
            "height": height,
            "duration": duration,
            "video_codec": video_codec,
            "needs_transcode": needs_transcode,
            "phash": phash,
            "error": None,
        }
    except Exception as e:
        return {"filepath": filepath, "error": str(e)}


def run_scan_and_organize() -> int:
    """
    Job principal: escaneia source + library_folders + organized e processa arquivos novos.
    """
    _require_storage()
    with media_file_operation_lock:
        return _run_scan_and_organize_locked()


def _run_scan_and_organize_locked() -> int:
    db = SessionLocal()
    try:
        job = ProcessingJob(
            job_type="scan_organize",
            status="running",
            started_at=datetime.datetime.utcnow(),
        )
        db.add(job)
        db.commit()

        # Converte .dng (RAW) em .jpg antes de escanear, para que sejam indexados
        # (o pics não reconhece .dng; o .jpg gerado entra no scan normalmente).
        try:
            from app.services.dng_converter import convert_dng_in_dir
            convert_dng_in_dir(settings.source_dir)
            for lib in getattr(settings, "library_folders", []) or []:
                convert_dng_in_dir(lib)
        except Exception as e:
            logger.error(f"[dng] pré-conversão falhou (ignorado): {e}")

        # Escaneia novos arquivos (source + library/organized)
        source_files = scan_source_directory(db)
        library_files = scan_library_directories(db)
        total = len(source_files) + len(library_files)
        job.total_items = total
        db.commit()

        processed = 0

        # 1. Processa arquivos do source (organiza/move)
        for filepath in source_files:
            try:
                media = organize_file(filepath, db)
                if media and not media.is_duplicate:
                    update_perceptual_hash(media, db)
                processed += 1
                job.processed_items = processed
                db.commit()
            except Exception as e:
                logger.error(f"Erro ao processar {filepath}: {e}")
                processed += 1
                job.processed_items = processed
                db.commit()
                continue

        # 2. Processa arquivos de library/organized em paralelo (em batches para controlar memória)
        workers = settings.scan_workers
        batch_size = 200  # Processa N arquivos por vez para não estourar memória
        logger.info(f"Processando {len(library_files)} arquivos de library com {workers} workers (batches de {batch_size})")

        for batch_start in range(0, len(library_files), batch_size):
            batch = library_files[batch_start:batch_start + batch_size]

            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(_preprocess_library_file, fp): fp for fp in batch}

                for future in as_completed(futures):
                    result = future.result()
                    filepath = result["filepath"]

                    if result.get("error"):
                        logger.error(f"Erro ao pré-processar {filepath}: {result['error']}")
                        processed += 1
                        job.processed_items = processed
                        continue

                    try:
                        file_hash = result["file_hash"]

                        # Verifica duplicata por hash (requer DB)
                        dup = db.query(Media).filter(
                            Media.sha256_hash == file_hash,
                            Media.is_duplicate == False,
                        ).first()

                        if dup:
                            media = Media(
                                original_path=filepath,
                                organized_path=filepath,
                                filename=result["filename"],
                                media_type=result["media_type"],
                                sha256_hash=file_hash,
                                is_duplicate=True,
                                duplicate_of_id=dup.id,
                                date_taken=result["media_date"],
                                date_file=result["date_file"],
                                is_organized=True,
                            )
                            db.add(media)
                        else:
                            media = Media(
                                original_path=filepath,
                                organized_path=filepath,
                                filename=result["filename"],
                                media_type=result["media_type"],
                                sha256_hash=file_hash,
                                date_taken=result["media_date"],
                                date_file=result["date_file"],
                                width=result["width"],
                                height=result["height"],
                                duration_seconds=result["duration"],
                                video_codec=result["video_codec"],
                                needs_transcode=result["needs_transcode"],
                                is_organized=True,
                            )
                            db.add(media)
                            db.flush()
                            # Atribui perceptual hash pré-calculado
                            if result["phash"]:
                                media.perceptual_hash = result["phash"]

                        processed += 1
                        job.processed_items = processed
                    except Exception as e:
                        logger.error(f"Erro ao adicionar {filepath}: {e}")
                        db.rollback()
                        processed += 1
                        job.processed_items = processed

            # Commit ao final de cada batch e libera memória da sessão
            db.commit()
            logger.info(f"Batch concluído: {processed}/{total} processados")

        try:
            cleanup_source_trash()
        except Exception as e:
            logger.error(f"Erro ao limpar source .trash: {e}")

        job.status = "completed"
        job.completed_at = datetime.datetime.utcnow()
        db.commit()

        logger.info(f"Scan completo: {processed}/{total} arquivos processados")
        return processed

    except Exception as e:
        logger.error(f"Erro no job de scan: {e}")
        job.status = "failed"
        job.error_message = str(e)
        db.commit()
        return 0
    finally:
        db.close()


def run_ai_processing(batch_size: int = None) -> int:
    """
    Processa mídias pendentes com Azure OpenAI Vision.
    """
    _require_storage()
    if not settings.ai_processing_enabled:
        logger.info("Processamento IA ignorado: AI_PROCESSING_ENABLED=false")
        return 0

    if batch_size is None:
        batch_size = settings.batch_size

    db = SessionLocal()
    try:
        job = ProcessingJob(
            job_type="ai_process",
            status="running",
            started_at=datetime.datetime.utcnow(),
        )
        db.add(job)
        db.commit()

        # Busca mídias não processadas pela IA
        pending = db.query(Media).filter(
            Media.ai_processed == False,
            Media.is_duplicate == False,
            Media.is_organized == True,
        ).limit(batch_size).all()

        job.total_items = len(pending)
        db.commit()

        processed = 0
        for media in pending:
            try:
                process_media_ai(media, db)
                processed += 1
                job.processed_items = processed
                db.commit()
            except Exception as e:
                logger.error(f"Erro ao processar IA para {media.filename}: {e}")
                continue

        job.status = "completed"
        job.completed_at = datetime.datetime.utcnow()
        db.commit()

        logger.info(f"IA processou {processed}/{len(pending)} mídias")
        return processed

    except Exception as e:
        logger.error(f"Erro no job de IA: {e}")
        job.status = "failed"
        job.error_message = str(e)
        db.commit()
        return 0
    finally:
        db.close()


def run_face_detection(batch_size: int = None) -> int:
    """
    Detecta rostos em mídias que ainda não foram processadas.
    """
    _require_storage()
    if batch_size is None:
        batch_size = settings.batch_size

    db = SessionLocal()
    try:
        job = ProcessingJob(
            job_type="face_detect",
            status="running",
            started_at=datetime.datetime.utcnow(),
        )
        db.add(job)
        safe_commit(db, "create face_detect job")

        # Busca imagens organizadas que não têm rostos processados
        pending = db.query(Media).filter(
            Media.media_type == "image",
            Media.is_duplicate == False,
            Media.is_organized == True,
            Media.faces_processed == False,
        ).limit(batch_size).all()

        job.total_items = len(pending)
        safe_commit(db, "set job.total_items")

        processed = 0
        total_faces = 0
        for media in pending:
            try:
                faces = process_faces_in_media(media, db)
                total_faces += len(faces)
                media.faces_processed = True
                processed += 1
                job.processed_items = processed
                if not safe_commit(db, f"processing media {media.filename}"):
                    # If commit fails, mark job as failed and continue gracefully
                    logger.error(f"Commit failed for media {media.filename}; continuing")
                    continue
            except Exception as e:
                logger.error(f"Erro na detecção facial para {media.filename}: {e}")
                media.faces_processed = True  # Marca como processado mesmo com erro para não retentar infinitamente
                safe_commit(db, f"error handling media {media.filename}")
                continue
                continue

        # Tenta agrupar rostos desconhecidos
        cluster_unknown_faces(db)

        job.status = "completed"
        job.completed_at = datetime.datetime.utcnow()
        safe_commit(db, "finalize face_detect job")

        logger.info(f"Faces: {processed} mídias, {total_faces} rostos detectados")
        return processed

    except Exception as e:
        logger.error(f"Erro no job de face detection: {e}")
        job.status = "failed"
        job.error_message = str(e)
        safe_commit(db, "fail face_detect job")
        return 0
    finally:
        db.close()


def _warmup_one(task: dict, size: int) -> bool:
    """Gera UM thumbnail (chamado em paralelo por threads). Sem acesso ao DB.

    `task` = {id, filename, media_type, source_path, cache_path}.
    Retorna True se o thumb ficou disponível (gerado agora ou já válido).
    """
    from app.services.organizer import generate_image_thumbnail, generate_video_thumbnail
    from PIL import Image

    source_path = task["source_path"]
    cache_path = task["cache_path"]
    if not source_path or not os.path.exists(source_path):
        return False

    # Pula se já existe cache atualizado (mais novo que a origem).
    if os.path.exists(cache_path):
        try:
            if os.path.getmtime(cache_path) >= os.path.getmtime(source_path):
                return True
        except Exception:
            pass

    try:
        if task["media_type"] == "image":
            return bool(generate_image_thumbnail(source_path, cache_path, size=size))
        thumb_tmp = cache_path + ".tmp"
        if generate_video_thumbnail(source_path, thumb_tmp):
            try:
                img = Image.open(thumb_tmp)
                img.thumbnail((size, size))
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(cache_path, format="JPEG", quality=80)
                return True
            except Exception:
                return False
            finally:
                if os.path.exists(thumb_tmp):
                    try:
                        os.unlink(thumb_tmp)
                    except Exception:
                        pass
        return False
    except Exception as e:
        logger.debug(f"Erro no thumbnail warmup ({source_path}): {e}")
        return False


def run_thumbnail_warmup(size: int = 300) -> int:
    """Pré-gera thumbnails em cache para mídias organizadas — AGRESSIVO.

    Otimizações vs. versão antiga (que fazia ~25k em semanas):
      - Paraleliza a geração com ThreadPoolExecutor (usa todos os núcleos;
        PIL libera o GIL na decodificação/resize, ffmpeg roda em subprocesso).
      - Commita o progresso EM LOTE (a cada N), não a cada item — evita 110k
        fsync do WAL, que era o maior gargalo.
      - Pré-filtra no próprio worker (arquivos já com cache válido não pesam).
    """
    from app.services.organizer import get_cached_thumbnail_path

    db = SessionLocal()
    try:
        existing = db.query(ProcessingJob).filter(
            ProcessingJob.job_type == "thumbnail_warmup",
            ProcessingJob.status == "running",
        ).first()
        if existing:
            logger.warning("Thumbnail warmup duplicado detectado; abortando segundo job.")
            return 0

        job = ProcessingJob(
            job_type="thumbnail_warmup",
            status="running",
            started_at=datetime.datetime.utcnow(),
        )
        db.add(job)
        db.commit()

        # Extrai os dados necessários (fora da thread) e fecha a leitura pesada.
        rows = db.query(
            Media.id, Media.filename, Media.media_type,
            Media.organized_path, Media.original_path,
        ).filter(
            Media.is_duplicate == False,
            Media.is_organized == True,
        ).all()

        tasks = [
            {
                "id": r.id,
                "filename": r.filename,
                "media_type": r.media_type,
                "source_path": r.organized_path or r.original_path,
                "cache_path": get_cached_thumbnail_path(r.id, r.filename),
            }
            for r in rows
        ]

        job.total_items = len(tasks)
        db.commit()

        # Nº de workers: I/O + CPU misto. min(32, cpus*4) é um bom teto p/ disco.
        max_workers = min(32, (os.cpu_count() or 4) * 4)
        processed = 0
        COMMIT_EVERY = 200

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_warmup_one, t, size) for t in tasks]
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    logger.debug(f"Thumbnail warmup task falhou: {e}")
                processed += 1
                if processed % COMMIT_EVERY == 0 or processed == len(tasks):
                    job.processed_items = processed
                    safe_commit(db, "warmup progress")

        job.status = "completed"
        job.completed_at = datetime.datetime.utcnow()
        job.processed_items = processed
        safe_commit(db, "finalize warmup")

        logger.info(f"Thumbnail warmup completo: {processed}/{len(tasks)} mídias (workers={max_workers})")
        return processed

    except Exception as e:
        logger.error(f"Erro no job de thumbnail warmup: {e}")
        job.status = "failed"
        job.error_message = str(e)
        safe_commit(db, "fail warmup")
        return 0
    finally:
        db.close()


def run_sync() -> dict:
    """
    Sincroniza o banco com o estado real das pastas organizadas.
    - Remove do banco arquivos que foram deletados do disco
    - Detecta arquivos movidos (mesmo filename em path diferente) e atualiza path
    - Adiciona arquivos novos encontrados na pasta organizada
    Não renomeia — o nome do arquivo nunca muda.
    """
    with media_file_operation_lock:
        return _run_sync_locked()


def _run_sync_locked() -> dict:
    db = SessionLocal()
    try:
        removed = 0
        moved = 0
        added = 0

        def update_media_path(media: Media, path: str) -> None:
            media.original_path = path
            media.organized_path = path
            media.filename = os.path.basename(path)
            media.is_organized = True
            media.missing_since = None

        # 1. Verifica arquivos que sumiram ou mudaram de lugar (INCLUI DUPLICATAS também!)
        all_media = db.query(Media).filter(
            Media.is_organized == True,
        ).all()

        for media in all_media:
            if media.organized_path and not os.path.exists(media.organized_path):
                # Arquivo sumiu do path original - tenta encontrar pelo nome
                all_library_dirs = [settings.organized_dir] + settings.library_folders
                found_path = None
                for lib_dir in all_library_dirs:
                    found_path = _find_file_by_name(media.filename, lib_dir)
                    if found_path:
                        break
                if found_path:
                    # Moveu de pasta - atualiza path (mantém faces, AI, tags, tudo)
                    update_media_path(media, found_path)
                    moved += 1
                    logger.info(f"Movido: {media.filename} -> {found_path}")
                else:
                    # Não encontrado por nome - marca como missing (limpeza só manual)
                    if not media.missing_since:
                        media.missing_since = datetime.datetime.utcnow()
                        logger.info(f"Não encontrado (marcado missing): {media.filename}")
            elif media.missing_since:
                # Arquivo reapareceu - limpa flag
                media.missing_since = None

        db.commit()

        # 2. Busca arquivos novos nas pastas organizadas (não estão no banco)
        all_library_dirs = [settings.organized_dir] + settings.library_folders
        for organized_dir in all_library_dirs:
            if not os.path.exists(organized_dir):
                continue
            for root, _dirs, files in os.walk(organized_dir):
                # Ignora pasta de thumbnails e trash
                if '.thumbnails' in root or '.trash' in root:
                    continue
                for filename in files:
                    # Ignora arquivos de transcodificação auxiliares
                    if '_transcoded' in filename or filename.endswith(('.lock', '.progress')):
                        continue
                    filepath = os.path.join(root, filename)
                    ext = Path(filepath).suffix.lower()
                    if ext not in settings.all_extensions:
                        continue

                    # Verifica se já está no banco por path
                    existing = db.query(Media).filter(
                        Media.organized_path == filepath
                    ).first()
                    if existing:
                        continue

                    # Arquivo novo - adiciona ao banco
                    try:
                        file_hash = compute_sha256(filepath)
                        moved_existing = next(
                            (
                                candidate for candidate in db.query(Media).filter(Media.sha256_hash == file_hash).all()
                                if candidate.organized_path and not os.path.exists(candidate.organized_path)
                            ),
                            None,
                        )
                        if moved_existing:
                            if moved_existing.organized_path != filepath:
                                update_media_path(moved_existing, filepath)
                                moved += 1
                                logger.info(f"Movido por hash: {filename} -> {filepath}")
                            continue

                        # Verifica duplicata por hash
                        dup = db.query(Media).filter(
                            Media.sha256_hash == file_hash,
                            Media.is_duplicate == False,
                        ).first()
                        if dup:
                            # Registra como duplicata no banco
                            media = Media(
                                original_path=filepath,
                                organized_path=filepath,
                                filename=filename,
                                media_type=get_media_type(filepath),
                                sha256_hash=file_hash,
                                is_duplicate=True,
                                duplicate_of_id=dup.id,
                                date_taken=get_media_date(filepath),
                                date_file=datetime.datetime.fromtimestamp(os.path.getmtime(filepath)),
                                is_organized=True,
                            )
                            db.add(media)
                            added += 1
                            continue

                        media_type = get_media_type(filepath)
                        media_date = get_media_date(filepath)

                        from app.services.organizer import get_image_dimensions, get_video_metadata
                        width, height, duration = None, None, None
                        video_codec = None
                        needs_transcode = False
                        if media_type == "image":
                            width, height = get_image_dimensions(filepath)
                        elif media_type == "video":
                            meta = get_video_metadata(filepath)
                            width, height = meta.get("width"), meta.get("height")
                            duration = meta.get("duration")
                            video_codec = meta.get("codec")
                            # Codecs suportados nativamente pelos browsers
                            web_codecs = {"h264", "hevc", "vp8", "vp9", "av1"}
                            if video_codec and video_codec not in web_codecs:
                                needs_transcode = True

                        media = Media(
                            original_path=filepath,
                            organized_path=filepath,
                            filename=filename,
                            media_type=media_type,
                            sha256_hash=file_hash,
                            date_taken=media_date,
                            date_file=datetime.datetime.fromtimestamp(os.path.getmtime(filepath)),
                            width=width,
                            height=height,
                            duration_seconds=duration,
                            video_codec=video_codec,
                            needs_transcode=needs_transcode,
                            is_organized=True,
                        )
                        db.add(media)
                        added += 1
                    except Exception as e:
                        logger.error(f"Erro ao adicionar {filepath}: {e}")
                        continue

        db.commit()
        result = {
            "removed": removed,
            "moved": moved,
            "added": added,
            "processed": removed + moved + added,
        }
        logger.info(f"Sync: {result}")
        return result

    except Exception as e:
        logger.error(f"Erro no sync: {e}")
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()


def run_sync_job() -> dict:
    """Job wrapper para registrar e executar sync."""
    job_id = _create_job("sync")
    try:
        result = run_sync()
        if isinstance(result, dict) and result.get("error"):
            _update_job(job_id, "failed", error_message=result.get("error"))
            return result

        processed_items = result.get("processed", None)
        total_items = result.get("total", None)
        _update_job(job_id, "completed", processed_items=processed_items, total_items=total_items)
        return result
    except Exception as e:
        _update_job(job_id, "failed", error_message=str(e))
        raise


def run_purge_missing_job() -> dict:
    """Job wrapper para registrar e executar purge missing."""
    _require_storage()
    job_id = _create_job("purge_missing")
    try:
        result = run_purge_missing()
        if isinstance(result, dict) and result.get("error"):
            _update_job(job_id, "failed", error_message=result.get("error"))
            return result

        removed = result.get("removed", None)
        _update_job(job_id, "completed", processed_items=removed, total_items=removed)
        return result
    except Exception as e:
        _update_job(job_id, "failed", error_message=str(e))
        raise


def run_database_audit() -> dict:
    """
    Auditoria do banco de dados para identificar inconsistências.
    - Conta arquivos por status (duplicatas, missing, etc)
    - Encontra referências órfãs (faces sem mídia)
    - Revalida contagem de mídia visível
    """
    db = SessionLocal()
    try:
        logger.info("Iniciando auditoria do banco...")
        
        # Contagem de mídia
        total_media = db.query(Media).count()
        non_duplicate = db.query(Media).filter(Media.is_duplicate == False).count()
        duplicates = db.query(Media).filter(Media.is_duplicate == True).count()
        organized = db.query(Media).filter(Media.is_organized == True).count()
        missing = db.query(Media).filter(Media.missing_since.isnot(None)).count()
        visible_count = db.query(Media).filter(
            Media.is_duplicate == False,
            Media.is_organized == True,
        ).count()
        
        # Faces órfãs (referência a mídia deletada)
        orphan_faces = db.query(Face).outerjoin(
            media_faces,
            Face.id == media_faces.c.face_id,
        ).filter(media_faces.c.media_id.is_(None)).count()
        
        report = {
            "total_media": total_media,
            "non_duplicate": non_duplicate,
            "duplicates": duplicates,
            "organized": organized,
            "missing": missing,
            "visible_count": visible_count,
            "orphan_faces": orphan_faces,
        }
        logger.info(f"Auditoria completa: {report}")
        return report
    except Exception as e:
        logger.error(f"Erro na auditoria: {e}")
        return {"error": str(e)}
    finally:
        db.close()


def _find_file_by_name(filename: str, base_dir: str) -> str | None:
    """Busca arquivo pelo nome nas subpastas do diretório organizado."""
    root_match = None
    for root, _dirs, files in os.walk(base_dir):
        if '.thumbnails' in root or '.trash' in root:
            continue
        if filename in files:
            path = os.path.join(root, filename)
            if root != base_dir:
                return path
            root_match = path
    return root_match


def _remove_media_and_faces(media: Media, db: Session):
    """Remove mídia e suas faces/associações do banco."""
    # Remove associações face-media
    for face in media.faces:
        face.media_items.remove(media)
        # Se a face não tem mais mídias, remove ela também
        if not face.media_items:
            db.delete(face)
    db.delete(media)


def run_purge_missing() -> dict:
    """
    Remove do banco todos os registros marcados como missing (arquivo não encontrado em disco).
    Essa operação é manual - só roda quando o usuário clica o botão.
    """
    db = SessionLocal()
    try:
        missing_media = db.query(Media).filter(Media.missing_since.isnot(None)).all()
        removed = 0
        for media in missing_media:
            _remove_media_and_faces(media, db)
            removed += 1
        db.commit()
        logger.info(f"Purge missing: {removed} registros removidos")
        return {"removed": removed}
    except Exception as e:
        logger.error(f"Erro no purge missing: {e}")
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()
