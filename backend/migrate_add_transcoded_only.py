"""
Migração: adiciona coluna transcoded_only na tabela albums.
Rodar uma vez na máquina do servidor:

    cd C:\src\pics\backend
    & "venv\Scripts\python.exe" migrate_add_transcoded_only.py
"""
import sqlite3
import sys
from pathlib import Path

# Localiza o banco seguindo a mesma lógica do config.py
env_path = Path(__file__).parent / ".env"
db_path = None
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            val = line.split("=", 1)[1].strip().strip('"').strip("'")
            db_path = val.replace("sqlite:///", "").replace("sqlite:////", "/")
            break

if not db_path:
    db_path = str(Path(__file__).parent / "pics.db")

print(f"Banco: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(albums)")
cols = {row[1] for row in cursor.fetchall()}

if "transcoded_only" in cols:
    print("Coluna transcoded_only já existe — nada a fazer.")
else:
    cursor.execute("ALTER TABLE albums ADD COLUMN transcoded_only INTEGER DEFAULT 0")
    conn.commit()
    print("Coluna transcoded_only adicionada com sucesso.")

conn.close()
