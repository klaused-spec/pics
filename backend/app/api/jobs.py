"""
Endpoints para gerenciar jobs de processamento.
"""
import datetime
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user
from app.models import ProcessingJob
from app.workers.processor import (
    run_scan_and_organize,
    run_ai_processing,
    run_face_detection,
    run_thumbnail_warmup,
    run_sync_job,
    run_purge_missing_job,
    run_database_audit,
    run_rclone_download_job,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


@router.get("/")
def list_jobs(
    current_user: dict = Depends(get_current_user),
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
def start_scan(
    current_user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Inicia job de scan e organização de novos arquivos."""
    background_tasks.add_task(run_scan_and_organize)
    return {"message": "Job de scan iniciado em background"}


@router.post("/rclone-download")
def start_rclone_download(
    current_user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Baixa arquivos dos remotes (OneDrive) via rclone para o source_dir."""
    if not settings.rclone_enabled:
        raise HTTPException(status_code=403, detail="rclone desativado nas configurações (rclone_enabled=false)")
    background_tasks.add_task(run_rclone_download_job)
    return {"message": "Job de download rclone iniciado em background"}


@router.get("/rclone-log")
def get_rclone_download_log(
    current_user: dict = Depends(get_current_user),
):
    """Retorna as últimas linhas de log do rclone para acompanhar na web."""
    from app.services.rclone_sync import get_rclone_log
    return {"lines": get_rclone_log()}


@router.post("/ai-process")
def start_ai_processing(
    current_user: dict = Depends(get_current_user),
    batch_size: int = Query(99999, ge=1, le=100000),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Inicia processamento com Azure OpenAI."""
    if not settings.ai_processing_enabled:
        raise HTTPException(status_code=403, detail="Processamento por IA desativado nas configurações")

    background_tasks.add_task(run_ai_processing, batch_size)
    return {"message": f"Job de IA iniciado (batch={batch_size})"}


@router.post("/face-detect")
def start_face_detection(
    current_user: dict = Depends(get_current_user),
    batch_size: int = Query(99999, ge=1, le=100000),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Inicia detecção facial."""
    background_tasks.add_task(run_face_detection, batch_size)
    return {"message": f"Job de detecção facial iniciado (batch={batch_size})"}


@router.post("/thumbnail-warmup")
def start_thumbnail_warmup(
    current_user: dict = Depends(get_current_user),
    size: int = Query(300, ge=50, le=800),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Inicia pré-geração de cache de thumbnails em background."""
    existing_job = db.query(ProcessingJob).filter(
        ProcessingJob.job_type == "thumbnail_warmup",
        ProcessingJob.status.in_(["pending", "running", "interrupted"]),
    ).first()
    if existing_job:
        raise HTTPException(
            status_code=409,
            detail="Thumbnail warmup já está em execução. Aguarde a conclusão antes de iniciar outro.",
        )

    background_tasks.add_task(run_thumbnail_warmup, size)
    return {"message": f"Job de warmup de thumbnails iniciado (size={size})"}


@router.post("/full-pipeline")
def start_full_pipeline(
    current_user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Executa pipeline completo: sync → scan → organizar → IA → faces. Processa TUDO pendente."""

    def full_pipeline():
        run_sync_job()
        run_scan_and_organize()
        # Processa tudo pendente (sem limite de batch)
        run_ai_processing(batch_size=99999)
        run_face_detection(batch_size=99999)

    background_tasks.add_task(full_pipeline)
    return {"message": "Pipeline completo iniciado em background"}


@router.post("/sync")
def start_sync(
    current_user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Sincroniza banco com pastas: detecta movidos, apagados e novos."""
    background_tasks.add_task(run_sync_job)
    return {"message": "Sync iniciado em background"}


@router.post("/check-mounts")
def check_mounts_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verifica status de todos os mount points (WSL/Linux) e tenta recuperar os stale."""
    from app.services.mount_checker import check_and_recover_library_mounts
    results = check_and_recover_library_mounts(settings.library_folders)
    
    summary = {
        "total": len(results),
        "ok": sum(1 for r in results.values() if r["status"] == "ok"),
        "stale": sum(1 for r in results.values() if r["status"] == "stale"),
        "recovered": sum(1 for r in results.values() if r.get("recovered", False)),
        "details": results,
    }
    return summary


@router.get("/audit")
def database_audit(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Realiza auditoria imediata do banco e retorna estatísticas."""
    result = run_database_audit()
    return result


@router.post("/purge-missing")
def start_purge_missing(
    current_user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Remove do banco todos os arquivos marcados como missing (não encontrados em disco)."""
    from app.models.models import Media
    missing_count = db.query(Media).filter(Media.missing_since.isnot(None)).count()
    if missing_count == 0:
        return {"message": "Nenhum arquivo missing para remover", "missing_count": 0}
    background_tasks.add_task(run_purge_missing_job)
    return {"message": f"Purge iniciado: {missing_count} arquivos missing serão removidos", "missing_count": missing_count}


@router.delete("/{job_id}")
def delete_job(
    job_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove um job do histórico."""
    job = db.query(ProcessingJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    
    db.delete(job)
    db.commit()
    return {"message": f"Job {job_id} removido do histórico"}


@router.delete("/")
def clear_jobs_history(
    current_user: dict = Depends(get_current_user),
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Limpa o histórico de jobs. Por padrão, não remove jobs em execução."""
    query = db.query(ProcessingJob)
    if not force:
        query = query.filter(ProcessingJob.status != "running")

    deleted_count = query.delete(synchronize_session=False)
    db.commit()

    return {
        "message": f"{deleted_count} job(s) removido(s) do histórico",
        "deleted": deleted_count,
        "force": force,
    }


@router.post("/reboot")
def reboot_server(
    current_user: dict = Depends(get_current_user),
):
    """Força reinicialização imediata do sistema operacional (shutdown -r -t 0)."""
    import subprocess
    import threading
    import sys

    def do_reboot():
        import time
        time.sleep(1)  # dá tempo para a resposta HTTP chegar
        if sys.platform == "win32":
            subprocess.run(["shutdown", "/r", "/t", "0"], check=False)
        else:
            subprocess.run(["shutdown", "-r", "-t", "0"], check=False)

    threading.Thread(target=do_reboot, daemon=True).start()
    return {"message": "Reinicialização agendada"}


@router.post("/restart-app")
def restart_app(
    current_user: dict = Depends(get_current_user),
):
    """Reinicia backend + Caddy sem reboot do PC.

    Estratégia Windows: lança um processo PowerShell filho ANTES de matar o
    Python. O filho dorme 3s (garante que a resposta HTTP chegou ao cliente),
    mata python.exe + caddy.exe e sobe restart-app.bat numa nova janela cmd.
    Como o PowerShell é iniciado com CREATE_NEW_PROCESS_GROUP e DETACHED, ele
    sobrevive ao taskkill do pai sem precisar de Agendador de Tarefas.
    """
    import subprocess
    import threading
    import sys
    import os

    def do_restart():
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[3]  # backend/app/api/jobs.py -> pics/
        if sys.platform == "win32":
            vbs = str(root / "restart-app.vbs")
            # wscript.exe lança o VBS fora de qualquer job/console do Windows,
            # completamente desacoplado do processo Python. O VBS por sua vez
            # lança o PowerShell que mata e reinicia tudo.
            subprocess.Popen(
                ["wscript.exe", vbs],
                creationflags=0x00000008,  # DETACHED_PROCESS
                close_fds=True,
            )
        else:
            restart_sh = str(root / "restart-app.sh")
            subprocess.Popen(
                ["bash", "-c", f"sleep 3 && bash '{restart_sh}'"],
                start_new_session=True,
                close_fds=True,
            )

    threading.Thread(target=do_restart, daemon=True).start()
    return {"message": "Reinicialização agendada. Backend e Caddy voltam em ~15 segundos."}
