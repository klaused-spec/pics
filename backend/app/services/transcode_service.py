"""
Transcodificação de vídeos de álbuns para H.264/AAC em pasta local.

Fluxo:
  1. POST /albums/{id}/transcode → cria registros AlbumTranscodeJob para cada vídeo do álbum
  2. Worker roda em thread pool, processa um vídeo por vez por álbum
  3. GET /albums/{id}/transcode/status → retorna progresso (% e status por vídeo)
  4. Quando um vídeo está 'done', o app mobile usa o output_path via endpoint /transcode/video/{job_id}
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

# Lock por album_id para não paralelizar o mesmo álbum
_album_locks: dict[int, threading.Lock] = {}
_album_locks_lock = threading.Lock()


def _get_album_lock(album_id: int) -> threading.Lock:
    with _album_locks_lock:
        if album_id not in _album_locks:
            _album_locks[album_id] = threading.Lock()
        return _album_locks[album_id]


def output_path_for(album_id: int, media_id: int, filename: str = "") -> str:
    base = settings.transcoded_videos_dir
    stem = Path(filename).stem if filename else str(media_id)
    name = f"{media_id}_{stem}_transcoded.mp4"
    return str(Path(base) / str(album_id) / name)


def ensure_transcode_jobs(db: Session, album_id: int, video_media_ids: list[int]) -> list[AlbumTranscodeJob]:
    """Cria jobs de transcodificação para os vídeos que ainda não têm job."""
    jobs = []
    for media_id in video_media_ids:
        existing = (
            db.query(AlbumTranscodeJob)
            .filter_by(album_id=album_id, media_id=media_id)
            .first()
        )
        if existing:
            jobs.append(existing)
            continue
        media_item = db.query(Media).filter_by(id=media_id).first()
        filename = media_item.filename if media_item else ""
        job = AlbumTranscodeJob(
            album_id=album_id,
            media_id=media_id,
            status="pending",
            output_path=output_path_for(album_id, media_id, filename),
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
    if not jobs:
        return {"status": "none", "percent": 0, "jobs": []}

    total = len(jobs)
    done = sum(1 for j in jobs if j.status == "done")
    failed = sum(1 for j in jobs if j.status == "failed")
    running = sum(1 for j in jobs if j.status == "running")
    pending = total - done - failed - running

    if done == total:
        overall = "done"
    elif failed == total:
        overall = "failed"
    elif running > 0 or pending > 0:
        overall = "running"
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


def _transcode_video(job_id: int) -> None:
    """Roda ffmpeg para transcodificar um vídeo. Chamado em thread separada."""
    db: Session = SessionLocal()
    try:
        job = db.query(AlbumTranscodeJob).filter_by(id=job_id).first()
        if not job:
            return
        if job.status == "done":
            return

        # Pega o filepath do vídeo original
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

        # Remove arquivo parcial anterior se existir
        if os.path.exists(output):
            os.remove(output)

        job.status = "running"
        db.commit()

        cmd = [
            settings.ffmpeg_path,
            "-y",
            "-i", filepath,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",           # qualidade boa sem peso excessivo
            "-vf", "scale='min(1280,iw)':-2",  # max 1280px largura, proporcional
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",  # mp4 começa a tocar antes de terminar o download
            output,
        ]

        logger.info(f"[transcode] job={job_id} media={job.media_id} -> {output}")
        result = subprocess.run(cmd, capture_output=True, timeout=3600)

        if result.returncode == 0 and os.path.isfile(output):
            job.status = "done"
            logger.info(f"[transcode] job={job_id} concluído")
            # Marca o registro Media com o caminho do transcoded
            media_rec = db.query(Media).filter_by(id=job.media_id).first()
            if media_rec:
                media_rec.transcoded_path = output
        else:
            job.status = "failed"
            job.error_message = result.stderr.decode(errors="replace")[-500:]
            logger.error(f"[transcode] job={job_id} falhou: {job.error_message}")

        db.commit()
    except Exception as e:
        logger.exception(f"[transcode] job={job_id} exceção: {e}")
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


def start_album_transcode(album_id: int, job_ids: list[int]) -> None:
    """Dispara transcodificação dos jobs em thread dedicada por álbum."""

    def _worker():
        lock = _get_album_lock(album_id)
        with lock:
            for job_id in job_ids:
                _transcode_video(job_id)

    t = threading.Thread(target=_worker, daemon=True, name=f"transcode-album-{album_id}")
    t.start()
