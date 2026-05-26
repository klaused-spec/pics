"""
API de configuração e backup/restore do banco de dados.
Backup inclui: banco SQLite (faces, AI, media) + .env (configs) em um ZIP.
"""
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/settings", tags=["settings"])

# Caminho do .env para persistir configs
ENV_PATH = Path(__file__).parent.parent.parent / ".env"


class PathsConfig(BaseModel):
    source_dir: str
    organized_dir: str
    trash_dir: str
    organization_pattern: str = "year/month"
    library_folders: list[str] = []


class PathsResponse(BaseModel):
    source_dir: str
    organized_dir: str
    trash_dir: str
    database_path: str
    organization_pattern: str
    library_folders: list[str]


@router.get("/paths", response_model=PathsResponse)
def get_paths():
    """Retorna configuração atual dos diretórios."""
    db_path = settings.database_url.replace("sqlite:///", "").replace("sqlite:////", "/")
    if db_path.startswith("./"):
        db_path = str(Path(__file__).parent.parent.parent / db_path[2:])
    return PathsResponse(
        source_dir=settings.source_dir,
        organized_dir=settings.organized_dir,
        trash_dir=settings.trash_dir,
        database_path=db_path,
        organization_pattern=settings.organization_pattern,
        library_folders=settings.library_folders,
    )


@router.put("/paths")
def update_paths(config: PathsConfig):
    """Atualiza diretórios e padrão de organização. Salva no .env e aplica em runtime."""
    # Valida padrão de organização
    if config.organization_pattern not in ("year/month", "year_month"):
        raise HTTPException(status_code=400, detail="Padrão inválido. Use 'year/month' ou 'year_month'")

    # Valida que os diretórios existem ou podem ser criados
    all_dirs = [
        ("source_dir", config.source_dir),
        ("organized_dir", config.organized_dir),
        ("trash_dir", config.trash_dir),
    ] + [(f"library_folders[{i}]", f) for i, f in enumerate(config.library_folders)]

    for name, path in all_dirs:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            raise HTTPException(status_code=400, detail=f"Não foi possível criar {name}: {e}")

    # Atualiza em runtime
    settings.source_dir = config.source_dir
    settings.organized_dir = config.organized_dir
    settings.trash_dir = config.trash_dir
    settings.organization_pattern = config.organization_pattern
    settings.library_folders = config.library_folders

    # Persiste no .env
    env_data = {
        "SOURCE_DIR": config.source_dir,
        "ORGANIZED_DIR": config.organized_dir,
        "TRASH_DIR": config.trash_dir,
        "ORGANIZATION_PATTERN": config.organization_pattern,
        "LIBRARY_FOLDERS": ",".join(config.library_folders),
    }
    _save_env(env_data)

    return {"status": "ok", "message": "Configurações atualizadas"}


@router.get("/backup")
def backup_database():
    """
    Backup completo em ZIP contendo:
    - pics.db (banco SQLite com: media, faces/persons, AI cache, albums, tags)
    - .env (configurações de diretórios)
    """
    db_path = settings.database_url.replace("sqlite:///", "").replace("sqlite:////", "/")
    if db_path.startswith("./"):
        db_path = str(Path(__file__).parent.parent.parent / db_path[2:])

    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Banco de dados não encontrado")

    backup_name = f"pics_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    backup_path = os.path.join(tempfile.gettempdir(), backup_name)

    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_path, "pics.db")
        if ENV_PATH.exists():
            zf.write(str(ENV_PATH), ".env")

    return FileResponse(
        backup_path,
        filename=backup_name,
        media_type="application/zip",
    )


@router.post("/restore")
async def restore_database(file: UploadFile = File(...)):
    """
    Restaura backup (ZIP ou .db). 
    ZIP pode conter: pics.db + .env
    Após restore, ajuste os paths em Settings se o HD mudou de ponto de montagem.
    """
    if not (file.filename.endswith(".db") or file.filename.endswith(".zip")):
        raise HTTPException(status_code=400, detail="Arquivo deve ser .zip ou .db")

    db_path = settings.database_url.replace("sqlite:///", "").replace("sqlite:////", "/")
    if db_path.startswith("./"):
        db_path = str(Path(__file__).parent.parent.parent / db_path[2:])

    # Salva backup do banco atual antes de substituir
    if os.path.exists(db_path):
        backup_current = db_path + f".before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(db_path, backup_current)

    content = await file.read()
    temp_dir = tempfile.mkdtemp()

    import sqlite3

    if file.filename.endswith(".zip"):
        # Extrai ZIP
        zip_path = os.path.join(temp_dir, "backup.zip")
        with open(zip_path, "wb") as f:
            f.write(content)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(temp_dir)

        # Restaura banco
        extracted_db = os.path.join(temp_dir, "pics.db")
        if not os.path.exists(extracted_db):
            shutil.rmtree(temp_dir)
            raise HTTPException(status_code=400, detail="ZIP não contém pics.db")

        try:
            conn = sqlite3.connect(extracted_db)
            conn.execute("SELECT count(*) FROM sqlite_master")
            conn.close()
        except Exception:
            shutil.rmtree(temp_dir)
            raise HTTPException(status_code=400, detail="pics.db no ZIP não é válido")

        shutil.move(extracted_db, db_path)

        # Restaura .env se presente
        extracted_env = os.path.join(temp_dir, ".env")
        if os.path.exists(extracted_env):
            shutil.copy2(extracted_env, str(ENV_PATH))

    else:
        # .db direto
        temp_db = os.path.join(temp_dir, "restore.db")
        with open(temp_db, "wb") as f:
            f.write(content)
        try:
            conn = sqlite3.connect(temp_db)
            conn.execute("SELECT count(*) FROM sqlite_master")
            conn.close()
        except Exception:
            shutil.rmtree(temp_dir)
            raise HTTPException(status_code=400, detail="Arquivo não é um banco SQLite válido")
        shutil.move(temp_db, db_path)

    shutil.rmtree(temp_dir, ignore_errors=True)
    return {"status": "ok", "message": "Restaurado! Reinicie o backend para aplicar."}


def _save_env(updates: dict):
    """Atualiza ou cria o arquivo .env com os valores fornecidos."""
    existing = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                existing[key.strip()] = val.strip()

    existing.update(updates)

    lines = [f"{k}={v}" for k, v in existing.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n")


@router.post("/reset")
def reset_all():
    """
    Zera TUDO: banco de dados (media, faces, AI, albums) + move organized de volta ao source.
    Preserva apenas o .env (configs de paths).
    """
    from app.core.database import engine, Base, SessionLocal
    from app.models import Media
    import sqlalchemy

    db_path = settings.database_url.replace("sqlite:///", "").replace("sqlite:////", "/")
    if db_path.startswith("./"):
        db_path = str(Path(__file__).parent.parent.parent / db_path[2:])

    # Move arquivos organized de volta ao source
    organized_dir = settings.organized_dir
    source_dir = settings.source_dir
    os.makedirs(source_dir, exist_ok=True)
    moved = 0
    if os.path.exists(organized_dir):
        for root, _dirs, files in os.walk(organized_dir):
            if '.thumbnails' in root:
                continue
            for fname in files:
                if '_transcoded' in fname or fname.endswith(('.lock', '.progress')):
                    continue
                src = os.path.join(root, fname)
                dest = os.path.join(source_dir, fname)
                if os.path.exists(dest):
                    base, ext = os.path.splitext(fname)
                    counter = 1
                    while os.path.exists(dest):
                        dest = os.path.join(source_dir, f"{base}_{counter}{ext}")
                        counter += 1
                shutil.move(src, dest)
                moved += 1

    # Recria banco do zero
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    return {"status": "ok", "message": f"Reset completo. {moved} arquivos movidos de volta ao source."}
