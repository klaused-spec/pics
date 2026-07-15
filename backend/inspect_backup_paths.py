import sqlite3
from pathlib import Path

path = Path('pics.db.pre_wsl_to_windows.bak')
conn = sqlite3.connect(path)
cur = conn.cursor()

for row in cur.execute("select name from sqlite_master where type='table'"):
    table = row[0]
    cols = [c[1] for c in cur.execute(f"pragma table_info({table})") if c[2].upper().startswith(('TEXT','VARCHAR','JSON'))]
    for col in cols:
        count = cur.execute(f"select count(*) from {table} where {col} like ?", ('%/mnt/g/%',)).fetchone()[0]
        if count:
            print(table, col, count)
conn.close()
