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
from app.services.organizer import scan_source_directory, scan_library_directories, organize_file, get_media_type, get_media_date, get_image_dimensions, get_video_metadata
from app.services.duplicates import update_perceptual_hash, check_duplicate, compute_perceptual_hash
from app.services.ai_vision import process_media_ai
from app.services.face_recognition_service import process_faces_in_media, cluster_unknown_faces
from app.services.organizer import compute_sha256

logger = logging.getLogger(__name__)


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
    db = SessionLocal()
    try:
        job = ProcessingJob(
            job_type="scan_organize",
            status="running",
            started_at=datetime.datetime.utcnow(),
        )
        db.add(job)
        db.commit()

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

        # 2. Processa arquivos de library/organized em paralelo
        workers = settings.scan_workers
        logger.info(f"Processando {len(library_files)} arquivos de library com {workers} workers")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_preprocess_library_file, fp): fp for fp in library_files}

            for future in as_completed(futures):
                result = future.result()
                filepath = result["filepath"]

                if result.get("error"):
                    logger.error(f"Erro ao pré-processar {filepath}: {result['error']}")
                    processed += 1
                    job.processed_items = processed
                    db.commit()
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
                    if processed % 50 == 0:
                        db.commit()
                except Exception as e:
                    logger.error(f"Erro ao adicionar {filepath}: {e}")
                    db.rollback()
                    processed += 1
                    job.processed_items = processed

        db.commit()

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
        db.commit()

        # Busca imagens organizadas que não têm rostos processados
        pending = db.query(Media).filter(
            Media.media_type == "image",
            Media.is_duplicate == False,
            Media.is_organized == True,
            Media.faces_processed == False,
        ).limit(batch_size).all()

        job.total_items = len(pending)
        db.commit()

        processed = 0
        total_faces = 0
        for media in pending:
            try:
                faces = process_faces_in_media(media, db)
                total_faces += len(faces)
                media.faces_processed = True
                processed += 1
                job.processed_items = processed
                db.commit()
            except Exception as e:
                logger.error(f"Erro na detecção facial para {media.filename}: {e}")
                media.faces_processed = True  # Marca como processado mesmo com erro para não retentar infinitamente
                db.commit()
                continue

        # Tenta agrupar rostos desconhecidos
        cluster_unknown_faces(db)

        job.status = "completed"
        job.completed_at = datetime.datetime.utcnow()
        db.commit()

        logger.info(f"Faces: {processed} mídias, {total_faces} rostos detectados")
        return processed

    except Exception as e:
        logger.error(f"Erro no job de face detection: {e}")
        job.status = "failed"
        job.error_message = str(e)
        db.commit()
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
    db = SessionLocal()
    try:
        removed = 0
        moved = 0
        added = 0

        # 1. Verifica arquivos que sumiram ou mudaram de lugar
        all_media = db.query(Media).filter(
            Media.is_organized == True,
            Media.is_duplicate == False,
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
                    media.organized_path = found_path
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
        result = {"removed": removed, "moved": moved, "added": added}
        logger.info(f"Sync: {result}")
        return result

    except Exception as e:
        logger.error(f"Erro no sync: {e}")
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()


def _find_file_by_name(filename: str, base_dir: str) -> str | None:
    """Busca arquivo pelo nome nas subpastas do diretório organizado."""
    for root, _dirs, files in os.walk(base_dir):
        if '.thumbnails' in root or '.trash' in root:
            continue
        if filename in files:
            return os.path.join(root, filename)
    return None


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
