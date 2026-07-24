"""
PICS - Personal Image & Content System
Aplicação principal FastAPI.
"""
import datetime
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.core.database import init_db, backup_env_to_db, restore_env_from_db, backup_db_to_zip
from app.api import auth_router, media_router, persons_router, jobs_router, albums_router, settings_router, mobile_router
from app.workers.processor import run_scan_and_organize, run_ai_processing, run_face_detection, run_sync, run_rclone_download_job, run_thumbnail_warmup

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
    restore_env_from_db()
    init_db()
    backup_env_to_db()
    zip_path = backup_db_to_zip()
    if zip_path:
        logger.info(f"Backup do banco criado: {zip_path}")
    elif settings.db_backup_dir:
        logger.warning(f"Backup do banco falhou (diretório indisponível?): {settings.db_backup_dir}")

    # Marca jobs "running" órfãos como "interrupted" (crash/restart anterior)
    from app.core.database import SessionLocal
    from app.models import ProcessingJob
    db = SessionLocal()
    try:
        orphan_jobs = db.query(ProcessingJob).filter(ProcessingJob.status == "running").all()
        for j in orphan_jobs:
            j.status = "interrupted"
            j.error_message = "Interrompido por restart do servidor"
            j.completed_at = datetime.datetime.utcnow()
        if orphan_jobs:
            db.commit()
            logger.info(f"Marcados {len(orphan_jobs)} jobs órfãos como interrupted")
    finally:
        db.close()

    if settings.scheduler_enabled:
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
        scheduler.add_job(
            run_thumbnail_warmup,
            "interval",
            minutes=settings.scan_interval_minutes + 2,
            id="thumbnail_warmup",
            replace_existing=True,
            next_run_time=datetime.datetime.now() + datetime.timedelta(seconds=30),
        )
        if settings.rclone_enabled:
            scheduler.add_job(
                run_rclone_download_job,
                "interval",
                minutes=settings.rclone_interval_minutes,
                id="rclone_download",
                replace_existing=True,
            )
        scheduler.start()
        logger.info("Scheduler iniciado")
    else:
        logger.info("Scheduler automatico desabilitado por configuracao")

    yield

    # Shutdown
    if settings.scheduler_enabled:
        scheduler.shutdown()
    logger.info("PICS encerrado")


app = FastAPI(
    title="PICS - Personal Image & Content System",
    description="Sistema organizador de fotos e vídeos com IA",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS para frontend - dinâmico baseado em .env
allowed_origins = []
allowed_origin_regex = None

for host in settings.allowed_hosts_list:
    # HTTP e HTTPS para o host especificado
    allowed_origins.append(f"http://{host}:{settings.frontend_port}")
    allowed_origins.append(f"https://{host}:{settings.frontend_port}")
    # Também aceita porta padrão (80/443) se for um domínio
    if host not in ["localhost", "127.0.0.1"]:
        allowed_origins.append(f"http://{host}")
        allowed_origins.append(f"https://{host}")

# Regex para aceitar também IPs locais (172.x.x.x, 192.168.x.x)
allowed_origin_regex = (
    r"^https?://(?:localhost|127\.0\.0\.1|"
    + "|".join(re.escape(h) for h in settings.allowed_hosts_list) +
    r"|\d{1,3}(?:\.\d{1,3}){3})"
    r":(?:" + str(settings.frontend_port) + r"|80|443)$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rotas
app.include_router(auth_router, prefix="/api")
app.include_router(media_router, prefix="/api")
app.include_router(persons_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(albums_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(mobile_router, prefix="/api")


@app.get("/api/health")
def health_check():
    from app.services.mount_checker import get_storage_status
    storage = get_storage_status()
    status = "ok" if storage["all_available"] else "storage_unavailable"
    return {
        "status": status,
        "service": "PICS",
        "storage": storage,
    }
