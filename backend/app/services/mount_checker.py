"""
Serviço para detectar disponibilidade de diretórios/unidades críticos.
Protege o pics.db contra operações em cima de unidades indisponíveis
(ex.: HD externo desconectado, rede caída, drive mapeado ausente).

Comportamento:
- check_critical_dirs() retorna lista de {path, available, reason}.
- all_critical_dirs_available() retorna bool rápido para guards nos jobs.
- get_storage_status() retorna dict completo para o /api/health.
- Cache interno de 10 s para evitar I/O excessivo em chamadas repetidas.
"""
import os
import time
import threading
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Cache para evitar checar disco a cada request HTTP
_cache_lock = threading.Lock()
_cache_result: Optional[dict] = None
_cache_ts: float = 0.0
_CACHE_TTL: float = 10.0  # segundos


def _check_dir(path: str) -> dict:
    """
    Verifica se um diretório está acessível (listável).
    Usa os.scandir() com timeout emulado via threading para Windows.
    Retorna {"path": path, "available": bool, "reason": str}.
    """
    result = {"available": False, "reason": "unknown"}

    def _probe():
        try:
            with os.scandir(path) as it:
                next(it, None)  # força acesso real ao FS
            result["available"] = True
            result["reason"] = "ok"
        except PermissionError:
            result["reason"] = "permission_denied"
        except FileNotFoundError:
            result["reason"] = "not_found"
        except OSError as e:
            result["reason"] = f"os_error: {e.strerror}"
        except Exception as e:
            result["reason"] = str(e)

    t = threading.Thread(target=_probe, daemon=True)
    t.start()
    t.join(timeout=3.0)  # 3 s máximo; drive lento/pendente trava aqui
    if t.is_alive():
        result["reason"] = "timeout"

    return {"path": path, "available": result["available"], "reason": result["reason"]}


def _get_critical_paths() -> list[str]:
    """Retorna os caminhos críticos configurados no settings."""
    from app.core.config import settings
    paths = set()
    if settings.source_dir:
        paths.add(settings.source_dir)
    if settings.organized_dir:
        paths.add(settings.organized_dir)
    if settings.rclone_dest_dir:
        paths.add(settings.rclone_dest_dir)
    for folder in (settings.library_folders or []):
        paths.add(folder)
    return list(paths)


def check_critical_dirs() -> list[dict]:
    """
    Verifica todos os diretórios críticos do app.
    Retorna lista de {"path": str, "available": bool, "reason": str}.
    """
    paths = _get_critical_paths()
    return [_check_dir(p) for p in paths]


def get_storage_status() -> dict:
    """
    Retorna status completo dos diretórios (cacheado por _CACHE_TTL segundos).
    Formato:
      {
        "all_available": bool,
        "unavailable": ["path1", ...],
        "details": [{"path":..., "available":..., "reason":...}, ...],
        "checked_at": float,
      }
    """
    global _cache_result, _cache_ts

    now = time.monotonic()
    with _cache_lock:
        if _cache_result is not None and (now - _cache_ts) < _CACHE_TTL:
            return _cache_result

    details = check_critical_dirs()
    unavailable = [d["path"] for d in details if not d["available"]]
    result = {
        "all_available": len(unavailable) == 0,
        "unavailable": unavailable,
        "details": details,
        "checked_at": time.time(),
    }

    if unavailable:
        logger.warning(f"[storage] Diretórios indisponíveis: {unavailable}")

    with _cache_lock:
        _cache_result = result
        _cache_ts = now

    return result


def all_critical_dirs_available() -> tuple[bool, list[str]]:
    """
    Retorno rápido: (True, []) se tudo OK, (False, [lista_indisponível]) se não.
    Usa cache interno de {_CACHE_TTL}s.
    """
    status = get_storage_status()
    return status["all_available"], status["unavailable"]


def invalidate_cache():
    """Força recheck na próxima chamada (útil após operação que pode ter alterado o FS)."""
    global _cache_ts
    with _cache_lock:
        _cache_ts = 0.0
