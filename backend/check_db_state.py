import sqlite3
from pathlib import Path

path = Path('pics.db')
print('path', path.resolve())
print('exists', path.exists())
if path.exists():
    print('size', path.stat().st_size)
    conn = sqlite3.connect(path)
    c = conn.cursor()
    try:
        print('has_media_table', c.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='media'").fetchone())
    except Exception as e:
        print('ERR media table check', e)
    try:
        print('media_count', c.execute('SELECT count(*) FROM media').fetchone())
    except Exception as e:
        print('ERR media count', e)
    try:
        cols = c.execute('PRAGMA table_info(media)').fetchall()
        print('media_cols', [row[1] for row in cols])
    except Exception as e:
        print('ERR pragma media', e)
    conn.close()
