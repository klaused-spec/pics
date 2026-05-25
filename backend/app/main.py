"""
PICS - Personal Image & Content System
Aplicação principal FastAPI.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.core.database import init_db
from app.api import media_router, persons_router, jobs_router, albums_router
from app.workers.processor import run_scan_and_organize, run_ai_processing, run_face_detection, run_sync

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Scheduler para tarefas periódicas
scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Inicializando PICS...")
    init_db()

    # Agenda scan periódico
    scheduler.add_job(
        run_scan_and_organize,
        "interval",
        minutes=settings.scan_interval_minutes,
        id="scan_organize",
        replace_existing=True,
    )
    scheduler.add_job(
        run_ai_processing,
        "interval",
        minutes=settings.scan_interval_minutes + 5,
        id="ai_process",
        replace_existing=True,
    )
    scheduler.add_job(
        run_face_detection,
        "interval",
        minutes=settings.scan_interval_minutes + 10,
        id="face_detect",
        replace_existing=True,
    )
    scheduler.add_job(
        run_sync,
        "interval",
        minutes=3,
        id="sync_files",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler iniciado")

    yield

    # Shutdown
    scheduler.shutdown()
    logger.info("PICS encerrado")


app = FastAPI(
    title="PICS - Personal Image & Content System",
    description="Sistema organizador de fotos e vídeos com IA",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS para frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rotas
app.include_router(media_router, prefix="/api")
app.include_router(persons_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(albums_router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "PICS"}
