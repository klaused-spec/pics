"""
Endpoints para gerenciar jobs de processamento.
"""
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import ProcessingJob
from app.workers.processor import run_scan_and_organize, run_ai_processing, run_face_detection, run_sync, run_purge_missing

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/")
def list_jobs(
    status: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Lista jobs de processamento."""
    query = db.query(ProcessingJob)
    if status:
        query = query.filter(ProcessingJob.status == status)

    jobs = query.order_by(ProcessingJob.created_at.desc()).limit(limit).all()

    return [
        {
            "id": j.id,
            "job_type": j.job_type,
            "status": j.status,
            "total_items": j.total_items,
            "processed_items": j.processed_items,
            "progress": (j.processed_items / j.total_items * 100) if j.total_items > 0 else 0,
            "error_message": j.error_message,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]


@router.post("/scan")
def start_scan(background_tasks: BackgroundTasks):
    """Inicia job de scan e organização de novos arquivos."""
    background_tasks.add_task(run_scan_and_organize)
    return {"message": "Job de scan iniciado em background"}


@router.post("/ai-process")
def start_ai_processing(
    batch_size: int = Query(99999, ge=1, le=100000),
    background_tasks: BackgroundTasks = None,
):
    """Inicia processamento com Azure OpenAI."""
    background_tasks.add_task(run_ai_processing, batch_size)
    return {"message": f"Job de IA iniciado (batch={batch_size})"}


@router.post("/face-detect")
def start_face_detection(
    batch_size: int = Query(99999, ge=1, le=100000),
    background_tasks: BackgroundTasks = None,
):
    """Inicia detecção facial."""
    background_tasks.add_task(run_face_detection, batch_size)
    return {"message": f"Job de detecção facial iniciado (batch={batch_size})"}


@router.post("/full-pipeline")
def start_full_pipeline(background_tasks: BackgroundTasks):
    """Executa pipeline completo: sync → scan → organizar → IA → faces. Processa TUDO pendente."""

    def full_pipeline():
        run_sync()
        run_scan_and_organize()
        # Processa tudo pendente (sem limite de batch)
        run_ai_processing(batch_size=99999)
        run_face_detection(batch_size=99999)

    background_tasks.add_task(full_pipeline)
    return {"message": "Pipeline completo iniciado em background"}


@router.post("/sync")
def start_sync(background_tasks: BackgroundTasks):
    """Sincroniza banco com pastas: detecta movidos, apagados e novos."""
    background_tasks.add_task(run_sync)
    return {"message": "Sync iniciado em background"}


@router.post("/purge-missing")
def start_purge_missing(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Remove do banco todos os arquivos marcados como missing (não encontrados em disco)."""
    from app.models.models import Media
    missing_count = db.query(Media).filter(Media.missing_since.isnot(None)).count()
    if missing_count == 0:
        return {"message": "Nenhum arquivo missing para remover", "missing_count": 0}
    background_tasks.add_task(run_purge_missing)
    return {"message": f"Purge iniciado: {missing_count} arquivos missing serão removidos", "missing_count": missing_count}
