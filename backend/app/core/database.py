from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy import text

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)
# If using SQLite, enable WAL journal mode and a busy timeout to reduce "database is locked" errors
if "sqlite" in settings.database_url:
    try:
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL;"))
            conn.execute(text("PRAGMA busy_timeout=5000;"))
    except Exception:
        # Avoid crashing on startup if PRAGMA fails; logs will show issues
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
