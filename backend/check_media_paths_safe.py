import sqlite3
from pathlib import Path

def safe_exists(p: Path):
    try:
        return p.exists()
    except Exception as e:
        return f'ERROR: {type(e).__name__}: {e}'

path = Path('pics.db')
conn = sqlite3.connect(path)
c = conn.cursor()
for media_id in [98455, 1, 10, 100000]:
    row = c.execute('SELECT id, filename, original_path, organized_path, is_organized FROM media WHERE id=?', (media_id,)).fetchone()
    print('\nROW', row)
    if row:
        orig = Path(row[2]) if row[2] else None
        org = Path(row[3]) if row[3] else None
        print('original exists', safe_exists(orig) if orig else None, orig)
        print('organized exists', safe_exists(org) if org else None, org)
conn.close()
