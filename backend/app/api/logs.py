"""
API de streaming de logs em tempo real via Server-Sent Events (SSE).

Duas fontes:
  GET /api/logs/stream          — SSE do processo principal (ring handler)
  GET /api/logs/workers         — lista arquivos de log dos slideshow workers
  GET /api/logs/worker/{name}   — últimas N linhas de um worker log
"""
import asyncio
import collections
import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.core.security import get_current_user
from app.api.media import _auth_stream

router = APIRouter(prefix="/logs", tags=["logs"])

# ── Buffer circular de log do processo principal ──────────────────────────────

MAX_LINES = 600

class _RingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: collections.deque[dict] = collections.deque(maxlen=MAX_LINES)
        self.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self.records.append({"ts": time.time(), "level": record.levelname, "msg": msg})
        except Exception:
            self.handleError(record)


_ring: _RingHandler | None = None


def get_ring_handler() -> _RingHandler:
    global _ring
    if _ring is None:
        _ring = _RingHandler()
        _ring.setLevel(logging.INFO)
        root = logging.getLogger()
        if not any(isinstance(h, _RingHandler) for h in root.handlers):
            root.addHandler(_ring)
    return _ring


# ── SSE do processo principal ─────────────────────────────────────────────────

async def _backend_stream(ring: _RingHandler):
    snapshot = list(ring.records)
    for rec in snapshot:
        line = rec["msg"].replace("\n", " ")
        yield f"data: {line}\n\n"
    last_len = len(snapshot)
    while True:
        await asyncio.sleep(0.5)
        current = list(ring.records)
        if len(current) > last_len:
            for rec in current[last_len:]:
                line = rec["msg"].replace("\n", " ")
                yield f"data: {line}\n\n"
        last_len = len(current)


@router.get("/stream")
async def stream_logs(request: Request, token: Optional[str] = None):
    """SSE: logs do processo FastAPI em tempo real. Aceita Bearer header ou ?token= query param."""
    _auth_stream(request, token)
    ring = get_ring_handler()
    return StreamingResponse(
        _backend_stream(ring),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Logs dos slideshow workers (arquivos em backend/logs/) ────────────────────

def _logs_dir() -> Path:
    return Path(__file__).parent.parent.parent / "logs"


@router.get("/workers")
def list_worker_logs(current_user: dict = Depends(get_current_user)):
    """Lista os arquivos de log dos slideshow workers, mais recente primeiro."""
    d = _logs_dir()
    if not d.exists():
        return {"files": []}
    files = sorted(
        [f for f in d.iterdir() if f.suffix == ".log"],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:50]
    return {"files": [{"name": f.name, "mtime": f.stat().st_mtime, "size": f.stat().st_size} for f in files]}


@router.get("/worker/{name}")
def get_worker_log(
    name: str,
    n: int = Query(default=300, le=2000),
    current_user: dict = Depends(get_current_user),
):
    """Retorna as últimas n linhas de um arquivo de log de worker."""
    # Segurança: só permite nomes sem path traversal
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Nome inválido")
    path = _logs_dir() / name
    if not path.exists() or path.suffix != ".log":
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return {"name": name, "lines": [l.rstrip() for l in lines[-n:]]}
