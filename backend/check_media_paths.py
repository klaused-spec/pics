import sqlite3
from pathlib import Path

path = Path('pics.db')
conn = sqlite3.connect(path)
c = conn.cursor()
for media_id in [98455]:
    row = c.execute('SELECT id, filename, original_path, organized_path, is_organized FROM media WHERE id=?', (media_id,)).fetchone()
    print('ROW', row)
    if row:
        orig = Path(row[2]) if row[2] else None
        org = Path(row[3]) if row[3] else None
        print('original exists', orig.exists() if orig else None, orig)
        print('organized exists', org.exists() if org else None, org)
        if orig and orig.exists():
            print('original size', orig.stat().st_size)
        if org and org.exists():
            print('organized size', org.stat().st_size)
conn.close()
