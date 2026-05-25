from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)
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

    # Verificar colunas existentes na tabela media
    cursor.execute("PRAGMA table_info(media)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    migrations = [
        ("media", "video_codec", "TEXT"),
        ("media", "needs_transcode", "INTEGER DEFAULT 0"),
    ]

    for table, col, col_type in migrations:
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")

    # Verificar tabelas novas (albums)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='albums'")
    if not cursor.fetchone():
        conn.commit()
        conn.close()
        return

    conn.commit()
    conn.close()
