"""Adiciona coluna display_rotation (0/90/180/270) na tabela media."""
import sqlite3, sys
db = sys.argv[1] if len(sys.argv) > 1 else 'backend/pics.db'
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("PRAGMA table_info(media)")
cols = [r[1] for r in cur.fetchall()]
if 'display_rotation' not in cols:
    cur.execute("ALTER TABLE media ADD COLUMN display_rotation INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    print("Coluna display_rotation adicionada.")
else:
    print("Coluna display_rotation já existe.")
conn.close()
