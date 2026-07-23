"""API para disponibilizar builds Android do app mobile."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/mobile", tags=["mobile"])

APK_DIR = Path(__file__).resolve().parents[3] / "mobile" / "pics-mobile-debug-apk"
APP_JSON = Path(__file__).resolve().parents[3] / "mobile" / "app.json"


def _app_version() -> str:
    """Lê version e versionCode do app.json do mobile."""
    try:
        import json
        data = json.loads(APP_JSON.read_text(encoding="utf-8"))
        v = data.get("expo", {}).get("version", "?")
        vc = data.get("expo", {}).get("android", {}).get("versionCode", "?")
        return f"{v} (build {vc})"
    except Exception:
        return "?"


def _apk_files():
    if not APK_DIR.exists():
        return []
    return sorted(
        (path for path in APK_DIR.iterdir() if path.is_file() and path.suffix.lower() == ".apk"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


@router.get("/apks")
def list_apks():
    version = _app_version()
    return {
        "version": version,
        "items": [
            {
                "filename": path.name,
                "size": path.stat().st_size,
                "modified_at": path.stat().st_mtime,
                "download_url": f"/api/mobile/apks/{path.name}",
                "version": version,
            }
            for path in _apk_files()
        ],
    }


@router.get("/apks/{filename}")
def download_apk(filename: str):
    path = (APK_DIR / filename).resolve()
    if path.parent != APK_DIR.resolve() or not path.is_file() or path.suffix.lower() != ".apk":
        raise HTTPException(status_code=404, detail="APK não encontrado")

    return FileResponse(
        path,
        media_type="application/vnd.android.package-archive",
        filename=path.name,
    )