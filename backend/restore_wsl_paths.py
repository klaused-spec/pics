import sqlite3
from pathlib import Path

src = Path('pics.db.pre_wsl_to_windows.bak')
dst = Path('pics.db.restored')
if dst.exists():
    print('Removing existing', dst)
    dst.unlink()

print('Copying', src, 'to', dst)
dst.write_bytes(src.read_bytes())

conn = sqlite3.connect(dst)
cur = conn.cursor()
cur.execute("UPDATE media SET original_path = replace(replace(original_path, '/mnt/g/', 'G:\\'), '/', '\\') WHERE original_path LIKE '/mnt/g/%'")
cur.execute("UPDATE media SET organized_path = replace(replace(organized_path, '/mnt/g/', 'G:\\'), '/', '\\') WHERE organized_path LIKE '/mnt/g/%'")
conn.commit()
print('original updated', cur.execute("select count(*) from media where original_path like 'G:%'").fetchone()[0])
print('organized updated', cur.execute("select count(*) from media where organized_path like 'G:%'").fetchone()[0])
print('sample', cur.execute("select id, original_path, organized_path from media where original_path like 'G:%' limit 5").fetchall())
conn.close()
