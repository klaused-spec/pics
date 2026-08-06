import sqlite3

conn = sqlite3.connect('pics.db')
c = conn.cursor()

print("=== TABELAS ===")
c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
print([r[0] for r in c.fetchall()])

print()
print("=== JOBS ATIVOS (pending/running) ===")
try:
    c.execute("""
        SELECT id, job_type, status, progress, created_at, updated_at, error_message
        FROM background_jobs
        WHERE status IN ('pending', 'running')
        ORDER BY created_at DESC LIMIT 20
    """)
    rows = c.fetchall()
    if rows:
        for row in rows:
            print(row)
    else:
        print("Nenhum job ativo")
except Exception as e:
    print(f"Erro: {e}")

print()
print("=== ULTIMOS 10 JOBS ===")
try:
    c.execute("""
        SELECT id, job_type, status, progress, created_at, updated_at, error_message
        FROM background_jobs
        ORDER BY created_at DESC LIMIT 10
    """)
    for row in c.fetchall():
        print(row)
except Exception as e:
    print(f"Erro: {e}")

conn.close()
