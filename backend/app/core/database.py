from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy import text

from app.core.config import settings

_is_sqlite = "sqlite" in settings.database_url

# Para SQLite, garante que o diretório do banco existe antes de criar o engine.
if _is_sqlite:
    _db_path = settings.database_url.replace("sqlite:///", "").replace("sqlite://", "")
    if _db_path:
        Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=30000;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
        finally:
            cursor.close()

    try:
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL;"))
            conn.execute(text("PRAGMA busy_timeout=30000;"))
    except Exception:
        pass

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def backup_db_to_zip() -> str | None:
    """
    Copia o pics.db (via SQLite VACUUM INTO) para um zip em DB_BACKUP_DIR.
    Retorna o caminho do zip criado, ou None se desativado/falhou.
    O backup é feito com VACUUM INTO para garantir consistência mesmo com WAL ativo.
    Mantém os últimos 7 zips (rotação por data no nome).
    """
    import logging
    import shutil
    import zipfile
    import datetime
    import glob

    log = logging.getLogger(__name__)

    backup_dir = settings.db_backup_dir.strip()
    if not backup_dir:
        return None

    backup_path = Path(backup_dir)
    try:
        backup_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log.warning(f"[backup] Não foi possível criar diretório de backup '{backup_dir}': {e}")
        return None

    if "sqlite" not in settings.database_url:
        return None

    db_file = settings.database_url.replace("sqlite:///", "").replace("sqlite://", "")
    if not db_file or not Path(db_file).exists():
        log.warning(f"[backup] Banco não encontrado em '{db_file}', backup ignorado")
        return None

    # Só faz backup 1x por dia — verifica se já existe zip de hoje
    today = datetime.datetime.now().strftime("%Y%m%d")
    existing_today = list(backup_path.glob(f"pics_{today}_*.zip"))
    if existing_today:
        log.info(f"[backup] Backup de hoje já existe ({existing_today[-1].name}), ignorando.")
        return None

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp_copy = backup_path / f"pics_{ts}.db"
    zip_path = backup_path / f"pics_{ts}.zip"

    try:
        # VACUUM INTO cria uma cópia limpa e consistente (fecha WAL antes de copiar)
        import sqlite3
        with sqlite3.connect(db_file) as conn:
            conn.execute(f"VACUUM INTO '{tmp_copy}'")

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_copy, "pics.db")

        tmp_copy.unlink(missing_ok=True)
        log.info(f"[backup] Banco salvo em '{zip_path}'")

        # Mantém só os últimos 7 backups
        zips = sorted(glob.glob(str(backup_path / "pics_*.zip")))
        for old in zips[:-7]:
            try:
                Path(old).unlink()
            except Exception:
                pass

        return str(zip_path)
    except Exception as e:
        log.warning(f"[backup] Falha ao fazer backup do banco: {e}")
        try:
            tmp_copy.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def init_db():
    Base.metadata.create_all(bind=engine)
    _run_migrations()


def _run_migrations():
    """Adiciona colunas novas em tabelas existentes (SQLite não suporta ALTER de forma robusta)."""
    import sqlite3
    if "sqlite" not in settings.database_url:
        return

    db_path = settings.database_url.replace("sqlite:///", "").replace("sqlite:////", "/")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Criar tabela kv_store para backup de configurações
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kv_store (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Verificar colunas existentes na tabela media
    cursor.execute("PRAGMA table_info(media)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    migrations = [
        ("media", "video_codec", "TEXT"),
        ("media", "needs_transcode", "INTEGER DEFAULT 0"),
        ("media", "missing_since", "TEXT"),
        ("media", "faces_processed", "INTEGER DEFAULT 0"),
        ("media", "missing_scans_count", "INTEGER DEFAULT 0"),
    ]

    for table, col, col_type in migrations:
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")

    # Índice composto para acelerar o manifesto de sync do app (filtro + order by),
    # evitando full scan nas páginas altas com dezenas de milhares de itens.
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_media_sync_manifest "
        "ON media (is_duplicate, is_organized, updated_at, id)"
    )

    # Verificar tabelas novas (albums)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='albums'")
    if not cursor.fetchone():
        conn.commit()
        conn.close()
        return

    conn.commit()
    conn.close()


def backup_env_to_db():
    """Salva o conteúdo do .env dentro do SQLite (tabela kv_store)."""
    import sqlite3
    from pathlib import Path

    env_path = Path(__file__).parent.parent.parent / ".env"
    if not env_path.exists():
        return

    db_path = settings.database_url.replace("sqlite:///", "").replace("sqlite:////", "/")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS kv_store (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute(
        "INSERT OR REPLACE INTO kv_store (key, value) VALUES (?, ?)",
        ("env_backup", env_path.read_text()),
    )
    conn.commit()
    conn.close()


def restore_env_from_db():
    """Se .env não existe, extrai do SQLite."""
    import sqlite3
    from pathlib import Path

    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        return False

    db_path = settings.database_url.replace("sqlite:///", "").replace("sqlite:////", "/")
    if not Path(db_path).exists():
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='kv_store'")
    if not cursor.fetchone():
        conn.close()
        return False

    cursor.execute("SELECT value FROM kv_store WHERE key = 'env_backup'")
    row = cursor.fetchone()
    conn.close()

    if row and row[0]:
        env_path.write_text(row[0])
        return True
    return False
