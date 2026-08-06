"""Reseta jobs failed com output_path=None para pending com path correto."""
import sqlite3
from pathlib import Path

DB = 'pics.db'
TRANSCODED_DIR = 'G:/photoide/transcoded_videos'

conn = sqlite3.connect(DB)
c = conn.cursor()

# Busca jobs failed sem output_path
c.execute("""
    SELECT j.id, j.album_id, j.media_id, m.filename, m.media_type, m.transcoded_path
    FROM album_transcode_jobs j
    JOIN media m ON m.id = j.media_id
    WHERE j.status = 'failed' AND (j.output_path IS NULL OR j.output_path = '')
""")
rows = c.fetchall()
print(f"Jobs failed sem output_path: {len(rows)}")

for job_id, album_id, media_id, filename, media_type, transcoded_path in rows:
    # Se já tem transcoded_path válido, usa direto
    if transcoded_path and Path(transcoded_path).exists():
        c.execute("UPDATE album_transcode_jobs SET status='done', output_path=?, error_message=NULL WHERE id=?",
                  (transcoded_path, job_id))
        print(f"  job {job_id} media {media_id} → done (aproveitou transcoded existente: {transcoded_path})")
    else:
        # Calcula output_path e reseta para pending
        stem = Path(filename).stem if filename else str(media_id)
        ext = '.jpg' if media_type == 'image' else '.mp4'
        output = str(Path(TRANSCODED_DIR) / f"{media_id}_{stem}_transcoded{ext}")
        c.execute("UPDATE album_transcode_jobs SET status='pending', output_path=?, error_message=NULL WHERE id=?",
                  (output, job_id))
        print(f"  job {job_id} media {media_id} → pending output={output}")

conn.commit()
conn.close()
print("Concluído.")
