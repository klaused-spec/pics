"""
Worker de slideshow — processo separado e leve, sem carregar FastAPI/face_recognition/matplotlib.
Usa slideshow_engine.py que só importa subprocess + sqlalchemy.
Uso: python slideshow_worker.py <job_id> <db_url> <ffmpeg> <ffprobe> <slideshows_dir> [music_dir]
"""
import sys
import os
import logging

BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, BASE_DIR)

if __name__ == "__main__":
    if len(sys.argv) < 6:
        print("Uso: python slideshow_worker.py <job_id> <db_url> <ffmpeg> <ffprobe> <slideshows_dir> [music_dir]")
        sys.exit(1)

    job_id    = int(sys.argv[1])
    db_url    = sys.argv[2]
    ffmpeg    = sys.argv[3]
    ffprobe   = sys.argv[4]
    sdir      = sys.argv[5]
    music_dir = sys.argv[6] if len(sys.argv) > 6 else ""

    log_path = os.path.join(BASE_DIR, "logs", f"slideshow_worker_{job_id}.log")
    os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    logger = logging.getLogger("slideshow_worker")
    logger.info(f"Worker iniciado: job_id={job_id} db={db_url}")

    try:
        from app.services.slideshow_engine import run_render
        run_render(
            job_id=job_id,
            db_url=db_url,
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            slideshows_dir=sdir,
            music_dir=music_dir,
        )
        logger.info(f"Worker concluído: job_id={job_id}")
    except Exception as exc:
        logger.exception(f"Worker falhou: job_id={job_id}: {exc}")
        sys.exit(1)
