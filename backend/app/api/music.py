"""
API para gerenciar músicas MP3 do slideshow.
"""
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.security import get_current_user
from app.api.media import _auth_stream

router = APIRouter(prefix="/music", tags=["music"])


def get_music_dir() -> Path:
    d = settings.music_dir.strip()
    if not d:
        raise HTTPException(status_code=400, detail="MUSIC_DIR não configurado no .env")
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p


@router.get("")
def list_music(current_user: dict = Depends(get_current_user)):
    """Lista todos os MP3 disponíveis."""
    d = get_music_dir()
    files = sorted(
        f.name for f in d.iterdir()
        if f.is_file() and f.suffix.lower() in (".mp3", ".m4a", ".aac", ".ogg", ".wav")
    )
    return {"files": files}


@router.post("/upload")
async def upload_music(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Faz upload de um arquivo de música."""
    d = get_music_dir()
    ext = Path(file.filename).suffix.lower()
    if ext not in (".mp3", ".m4a", ".aac", ".ogg", ".wav"):
        raise HTTPException(status_code=400, detail="Formato não suportado")
    dest = d / file.filename
    content = await file.read()
    dest.write_bytes(content)
    return {"ok": True, "filename": file.filename}


@router.delete("/{filename}")
def delete_music(filename: str, current_user: dict = Depends(get_current_user)):
    """Remove um arquivo de música."""
    d = get_music_dir()
    p = d / filename
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    # Segurança: impede path traversal
    if not str(p.resolve()).startswith(str(d.resolve())):
        raise HTTPException(status_code=400, detail="Caminho inválido")
    p.unlink()
    return {"ok": True}


@router.get("/stream/{filename}")
def stream_music(filename: str, request: Request, token: Optional[str] = None):
    """Stream de um arquivo de música. Aceita Bearer header ou ?token= query param."""
    _auth_stream(request, token)
    d = get_music_dir()
    p = d / filename
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    if not str(p.resolve()).startswith(str(d.resolve())):
        raise HTTPException(status_code=400, detail="Caminho inválido")
    return FileResponse(str(p), media_type="audio/mpeg")
