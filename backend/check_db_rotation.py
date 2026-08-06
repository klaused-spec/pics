import sqlite3
conn = sqlite3.connect('pics.db')
c = conn.cursor()
total = c.execute('SELECT COUNT(*) FROM media WHERE is_duplicate=0').fetchone()[0]
with_rot = c.execute('SELECT COUNT(*) FROM media WHERE is_duplicate=0 AND display_rotation != 0').fetchone()[0]
zero = c.execute('SELECT COUNT(*) FROM media WHERE is_duplicate=0 AND display_rotation = 0').fetchone()[0]
vids = c.execute('SELECT filename, display_rotation FROM media WHERE media_type="video" AND is_duplicate=0 AND display_rotation != 0 LIMIT 5').fetchall()
print(f'Total nao-duplicatas: {total}')
print(f'  display_rotation != 0: {with_rot}')
print(f'  display_rotation == 0: {zero}')
print('Amostras video com rotation:')
for f, r in vids:
    print(f'  {f}: rotation={r}')
conn.close()
