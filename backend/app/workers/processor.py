"""
Worker para processamento em background.
Gerencia jobs de scan, organização, análise IA e detecção facial.
"""
import os
import logging
import datetime
from pathlib import Path
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.config import settings
from app.models import Media, ProcessingJob, Face, media_faces
from app.services.organizer import scan_source_directory, organize_file, get_media_type, get_media_date
from app.services.duplicates import update_perceptual_hash, check_duplicate, compute_perceptual_hash
from app.services.ai_vision import process_media_ai
from app.services.face_recognition_service import process_faces_in_media, cluster_unknown_faces
from app.services.organizer import compute_sha256

logger = logging.getLogger(__name__)


def run_scan_and_organize() -> int:
    """
    Job principal: escaneia a pasta de origem e organiza arquivos novos.
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

        # Escaneia novos arquivos
        new_files = scan_source_directory(db)
        job.total_items = len(new_files)
        db.commit()

        processed = 0
        for filepath in new_files:
            try:
                media = organize_file(filepath, db)
                if media and not media.is_duplicate:
                    # Calcula perceptual hash
                    update_perceptual_hash(media, db)
                processed += 1
                job.processed_items = processed
                db.commit()
            except Exception as e:
                logger.error(f"Erro ao processar {filepath}: {e}")
                continue

        job.status = "completed"
        job.completed_at = datetime.datetime.utcnow()
        db.commit()

        logger.info(f"Scan completo: {processed}/{len(new_files)} arquivos processados")
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
        # (exclui mídias que já estão na tabela media_faces)
        from sqlalchemy import not_, exists
        from app.models import media_faces

        processed_ids = db.query(media_faces.c.media_id).distinct()

        pending = db.query(Media).filter(
            Media.media_type == "image",
            Media.is_duplicate == False,
            Media.is_organized == True,
            ~Media.id.in_(processed_ids),
        ).limit(batch_size).all()

        job.total_items = len(pending)
        db.commit()

        processed = 0
        total_faces = 0
        for media in pending:
            try:
                faces = process_faces_in_media(media, db)
                total_faces += len(faces)
                processed += 1
                job.processed_items = processed
                db.commit()
            except Exception as e:
                logger.error(f"Erro na detecção facial para {media.filename}: {e}")
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
                    # Moveu de pasta - atualiza path
                    media.organized_path = found_path
                    moved += 1
                    logger.info(f"Movido: {media.filename} -> {found_path}")
                else:
                    # Apagado - remove do banco (e faces associadas)
                    _remove_media_and_faces(media, db)
                    removed += 1
                    logger.info(f"Removido: {media.filename}")

        db.commit()

        # 2. Busca arquivos novos nas pastas organizadas (não estão no banco)
        all_library_dirs = [settings.organized_dir] + settings.library_folders
        for organized_dir in all_library_dirs:
            if not os.path.exists(organized_dir):
                continue
            for root, _dirs, files in os.walk(organized_dir):
                # Ignora pasta de thumbnails
                if '.thumbnails' in root:
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

                    # Verifica por filename (pode ter vindo de move)
                    existing_by_name = db.query(Media).filter(
                        Media.filename == filename,
                        Media.is_duplicate == False,
                    ).first()
                    if existing_by_name:
                        continue

                    # Arquivo novo - adiciona ao banco
                    try:
                        file_hash = compute_sha256(filepath)
                        # Verifica duplicata por hash
                        dup = db.query(Media).filter(Media.sha256_hash == file_hash).first()
                        if dup:
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
        if '.thumbnails' in root:
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
