"""API para disponibilizar builds Android do app mobile."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import get_current_user, verify_token

router = APIRouter(prefix="/mobile", tags=["mobile"])
optional_security = HTTPBearer(auto_error=False)

APK_DIR = Path(__file__).resolve().parents[3] / "mobile" / "pics-mobile-debug-apk"


async def get_current_user_for_download(
    token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
):
    if credentials:
        return verify_token(credentials.credentials)
    if token:
        return verify_token(token)
    raise HTTPException(status_code=401, detail="Token ausente")


def _apk_files():
    if not APK_DIR.exists():
        return []
    return sorted(
        (path for path in APK_DIR.iterdir() if path.is_file() and path.suffix.lower() == ".apk"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


@router.get("/apks")
def list_apks(current_user: dict = Depends(get_current_user)):
    return {
        "items": [
            {
                "filename": path.name,
                "size": path.stat().st_size,
                "modified_at": path.stat().st_mtime,
                "download_url": f"/api/mobile/apks/{path.name}",
            }
            for path in _apk_files()
        ]
    }


@router.get("/apks/{filename}")
def download_apk(filename: str, current_user: dict = Depends(get_current_user_for_download)):
    path = (APK_DIR / filename).resolve()
    if path.parent != APK_DIR.resolve() or not path.is_file() or path.suffix.lower() != ".apk":
        raise HTTPException(status_code=404, detail="APK não encontrado")

    return FileResponse(
        path,
        media_type="application/vnd.android.package-archive",
        filename=path.name,
    )