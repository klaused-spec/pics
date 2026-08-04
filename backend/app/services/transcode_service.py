"""
Otimização de mídias de álbuns para consumo rápido via internet no app mobile.

Fotos  → JPEG 1920px max, qualidade 82, strip EXIF pesado  (salvo como {id}_opt.jpg)
Vídeos → H.264 + AAC, max 1280px, faststart              (salvo como {id}_opt.mp4)

Fluxo:
  1. POST /albums/{id}/transcode → cria AlbumTranscodeJob para cada mídia do álbum
  2. Worker processa em sequência (um álbum por vez)
  3. GET /albums/{id}/transcode/status → progresso
  4. GET /albums/transcode/video/{job_id} → serve o arquivo otimizado
"""
import os
import subprocess
import logging
import threading
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import AlbumTranscodeJob, Media

logger = logging.getLogger(__name__)

# Lock por album_id — processa um álbum por vez para não saturar CPU/disco
_album_locks: dict[int, threading.Lock] = {}
_album_locks_lock = threading.Lock()


def _get_album_lock(album_id: int) -> threading.Lock:
    with _album_locks_lock:
        if album_id not in _album_locks:
            _album_locks[album_id] = threading.Lock()
        return _album_locks[album_id]


def _safe_name(name: str) -> str:
    """Converte nome para uso seguro em path (sem chars especiais)."""
    import re
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name or "album"


def output_path_for(album_id: int, media_id: int, media_type: str,
                    album_name: str = "", media_filename: str = "") -> str:
    base = settings.transcoded_videos_dir
    ext = ".jpg" if media_type == "image" else ".mp4"
    # Todos os arquivos na raiz do diretório de transcodificados, sem subpastas por álbum.
    # Usa media_id como prefixo para garantir unicidade entre álbuns.
    if media_filename:
        stem = Path(media_filename).stem
        fname = f"{media_id}_{_safe_name(stem)}_transcoded{ext}"
    else:
        fname = f"{media_id}_transcoded{ext}"
    return str(Path(base) / fname)


def ensure_transcode_jobs(db: Session, album_id: int, media_ids: list[int]) -> list[AlbumTranscodeJob]:
    """Cria jobs de otimização para todas as mídias do álbum que ainda não têm job."""
    from app.models import Album
    album = db.query(Album).filter_by(id=album_id).first()
    album_name = album.name if album else ""
    jobs = []
    for media_id in media_ids:
        existing = (
            db.query(AlbumTranscodeJob)
            .filter_by(album_id=album_id, media_id=media_id)
            .first()
        )
        if existing:
            jobs.append(existing)
            continue
        media_item = db.query(Media).filter_by(id=media_id).first()
        media_type = media_item.media_type if media_item else "video"
        media_filename = media_item.filename if media_item else ""
        job = AlbumTranscodeJob(
            album_id=album_id,
            media_id=media_id,
            status="pending",
            output_path=output_path_for(album_id, media_id, media_type, album_name, media_filename),
        )
        db.add(job)
        jobs.append(job)
    db.commit()
    for j in jobs:
        db.refresh(j)
    return jobs


def get_album_transcode_status(db: Session, album_id: int) -> dict:
    """Retorna progresso geral e detalhes por vídeo."""
    jobs = db.query(AlbumTranscodeJob).filter_by(album_id=album_id).all()
    # Ignora jobs cancelados
    jobs = [j for j in jobs if j.status != "cancelled"]
    if not jobs:
        return {"status": "none", "percent": 0, "jobs": []}

    total = len(jobs)
    done = sum(1 for j in jobs if j.status == "done")
    failed = sum(1 for j in jobs if j.status == "failed")
    running = sum(1 for j in jobs if j.status == "running")
    pending = sum(1 for j in jobs if j.status == "pending")

    if done == total:
        overall = "done"
    elif failed == total:
        overall = "failed"
    elif running > 0:
        overall = "running"
    elif pending > 0:
        overall = "pending"
    else:
        overall = "partial"

    percent = round(done / total * 100) if total > 0 else 0

    return {
        "status": overall,
        "percent": percent,
        "total": total,
        "done": done,
        "failed": failed,
        "running": running,
        "pending": pending,
        "jobs": [
            {
                "job_id": j.id,
                "media_id": j.media_id,
                "status": j.status,
                "output_path": j.output_path,
                "error": j.error_message,
            }
            for j in jobs
        ],
    }


def _optimize_job(job_id: int) -> None:
    """Otimiza uma mídia (foto ou vídeo) para consumo rápido via internet."""
    db: Session = SessionLocal()
    try:
        job = db.query(AlbumTranscodeJob).filter_by(id=job_id).first()
        if not job or job.status == "done":
            return
        # Se ainda estiver "running" de uma sessão anterior, trata como pendente
        if job.status == "running":
            job.status = "pending"
            db.commit()

        media = db.query(Media).filter_by(id=job.media_id).first()
        if not media:
            job.status = "failed"
            job.error_message = "Mídia não encontrada"
            db.commit()
            return

        filepath = media.organized_path or media.original_path
        if not filepath or not os.path.isfile(filepath):
            job.status = "failed"
            job.error_message = f"Arquivo não encontrado: {filepath}"
            db.commit()
            return

        output = job.output_path
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        if os.path.exists(output):
            os.remove(output)

        job.status = "running"
        db.commit()

        if media.media_type == "image":
            _optimize_image(filepath, output)
        else:
            _optimize_video(filepath, output)

        if os.path.isfile(output):
            job.status = "done"
            logger.info(f"[opt] job={job_id} media={job.media_id} done")
            import datetime as _dt
            media_rec = db.query(Media).filter_by(id=job.media_id).first()
            if media_rec:
                media_rec.transcoded_path = output
                # Atualiza updated_at para o sync incremental do app detectar a mudança
                media_rec.updated_at = _dt.datetime.utcnow()
        else:
            job.status = "failed"
            job.error_message = "Arquivo de saída não gerado"
            logger.error(f"[opt] job={job_id} falhou")

        db.commit()
    except Exception as e:
        logger.exception(f"[opt] job={job_id} exceção: {e}")
        try:
            job = db.query(AlbumTranscodeJob).filter_by(id=job_id).first()
            if job:
                job.status = "failed"
                job.error_message = str(e)[:500]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def _optimize_image(src: str, dst: str) -> None:
    """Redimensiona foto para 1920px max e salva como JPEG otimizado."""
    from PIL import Image as PilImage
    PilImage.MAX_IMAGE_PIXELS = None
    with PilImage.open(src) as img:
        img = img.convert("RGB")
        w, h = img.size
        max_side = 1920
        if w > max_side or h > max_side:
            ratio = min(max_side / w, max_side / h)
            img = img.resize((int(w * ratio), int(h * ratio)), PilImage.LANCZOS)
        img.save(dst, "JPEG", quality=82, optimize=True, progressive=True)


_qsv_available_cache: bool | None = None

def _qsv_available() -> bool:
    global _qsv_available_cache
    if _qsv_available_cache is None:
        try:
            probe = subprocess.run(
                [settings.ffmpeg_path, "-hide_banner", "-encoders"],
                capture_output=True, text=True, timeout=5
            )
            _qsv_available_cache = "h264_qsv" in probe.stdout
        except Exception:
            _qsv_available_cache = False
    return _qsv_available_cache


def _optimize_video(src: str, dst: str) -> None:
    """Transcodifica vídeo para H.264/AAC com faststart. Usa Intel QSV se disponivel."""
    scale_filter = "scale='trunc(min(960,iw)/2)*2':'trunc(ow/a/2)*2'"
    if _qsv_available():
        cmd = [
            settings.ffmpeg_path, "-y",
            "-hwaccel", "qsv", "-hwaccel_output_format", "qsv",
            "-i", src,
            "-vf", f"scale_qsv=w='trunc(min(960,iw)/2)*2':h=-1",
            "-c:v", "h264_qsv",
            "-global_quality", "32",
            "-c:a", "aac", "-b:a", "96k",
            "-movflags", "+faststart",
            dst,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=3600)
        if result.returncode == 0:
            logger.info(f"[opt] h264_qsv OK: {Path(dst).name}")
            return
        logger.warning(f"[opt] QSV falhou, usando CPU: {result.stderr.decode(errors='replace')[-200:]}")
    # Fallback CPU — limita threads para não saturar todos os núcleos
    import os as _os
    cpu_threads = str(max(1, (_os.cpu_count() or 4) // 2))
    cmd = [
        settings.ffmpeg_path, "-y",
        "-i", src,
        "-c:v", "libx264", "-preset", "fast", "-crf", "28",
        "-threads", cpu_threads,
        "-vf", scale_filter,
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        dst,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=3600)
    if result.returncode != 0:
        err = result.stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"ffmpeg falhou: {err}")


def start_album_transcode(album_id: int, job_ids: list[int]) -> None:
    """Dispara otimização dos jobs em thread dedicada por álbum."""

    def _worker():
        lock = _get_album_lock(album_id)
        with lock:
            for job_id in job_ids:
                _optimize_job(job_id)

    t = threading.Thread(target=_worker, daemon=True, name=f"opt-album-{album_id}")
    t.start()
