import sqlite3
conn = sqlite3.connect('pics.db')
c = conn.cursor()

print("=== Jobs failed ===")
c.execute("SELECT id, album_id, media_id, status, output_path, error_message FROM album_transcode_jobs WHERE status='failed' ORDER BY album_id")
for row in c.fetchall():
    print(row)

print()
print("=== Resumo por album/status ===")
c.execute("SELECT album_id, status, COUNT(*) FROM album_transcode_jobs GROUP BY album_id, status ORDER BY album_id, status")
for row in c.fetchall():
    print(row)

conn.close()
