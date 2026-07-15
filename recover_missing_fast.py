#!/usr/bin/env python3
"""
Fast recovery de arquivos missing no /mnt/g (WSL).
Em vez de verificar um por um, usa os timestamps para identificar 
os que foram marcados faltando quando o HD desplugou.
"""
import os
import sys
import sqlite3
import datetime
from pathlib import Path

os.chdir(os.path.join(os.path.dirname(__file__), "backend"))
sys.path.insert(0, os.getcwd())

from app.core.config import settings

def fast_recover_wsl_mount():
    """
    Estratégia rápida:
    1. Identifica quando o HD foi marcado como missing (pega o timestamp mais recente)
    2. Reseta todos os missing criados naquele horário (foram do mesmo evento)
    3. Deixa o sync normal fazer o resto
    """
    db_path = settings.database_url.replace("sqlite:///", "").replace("sqlite:////", "/")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("⚡ FAST RECOVERY - Arquivos missing no /mnt/g")
    print("=" * 60)
    
    # 1. Busca todos os missing
    cursor.execute("""
        SELECT COUNT(*) FROM media WHERE missing_since IS NOT NULL
    """)
    total_missing = cursor.fetchone()[0]
    print(f"\n📊 Total de arquivos missing: {total_missing}")
    
    if total_missing == 0:
        print("✓ Nenhum arquivo missing!")
        conn.close()
        return
    
    # 2. Busca os missing com /mnt em organized_path ou original_path
    cursor.execute("""
        SELECT COUNT(*) FROM media 
        WHERE missing_since IS NOT NULL 
        AND (organized_path LIKE '/mnt/%' OR original_path LIKE '/mnt/%')
    """)
    mnt_missing = cursor.fetchone()[0]
    print(f"🎯 Missing no /mnt (WSL): {mnt_missing}")
    
    # 3. Pega o timestamp mais recente (último desplugue)
    cursor.execute("""
        SELECT MAX(missing_since) FROM media WHERE missing_since IS NOT NULL
    """)
    last_missing_time = cursor.fetchone()[0]
    print(f"📅 Último evento: {last_missing_time}")
    
    # 4. Se tem arquivos no /mnt que agora estão acessíveis, marca como recuperados
    if last_missing_time:
        # Pega todos os missing criados no mesmo horário (mesma desconexão)
        # Filtra para só os que estão em /mnt
        cursor.execute("""
            SELECT id, organized_path, original_path FROM media
            WHERE missing_since IS NOT NULL 
            AND (organized_path LIKE '/mnt/%' OR original_path LIKE '/mnt/%')
            ORDER BY organized_path
        """)
        
        candidates = cursor.fetchall()
        print(f"\n🔍 Verificando {len(candidates)} arquivos em /mnt...")
        
        recovered = 0
        still_missing = 0
        
        for media_id, org_path, orig_path in candidates:
            # Tenta acessar o arquivo
            for path in [org_path, orig_path]:
                if path and os.path.exists(path):
                    cursor.execute("""
                        UPDATE media SET missing_since = NULL, missing_scans_count = 0
                        WHERE id = ?
                    """, (media_id,))
                    recovered += 1
                    break
            else:
                still_missing += 1
        
        conn.commit()
        
        print(f"\n✓ Recuperados: {recovered}")
        print(f"✗ Ainda missing: {still_missing}")
        
        # 5. Reseta missing_scans_count para 0 em todos os /mnt (para o sync refazer corretamente)
        cursor.execute("""
            UPDATE media SET missing_scans_count = 0
            WHERE organized_path LIKE '/mnt/%' OR original_path LIKE '/mnt/%'
        """)
        conn.commit()
        
        print(f"\n✨ Reset concluído!")
        print(f"\n💡 Próximo passo: O sync automático vai verificar os arquivos")
        print(f"   ou você pode rodar: curl -X POST http://localhost:8000/api/jobs/sync")
    
    # 6. Status final
    cursor.execute("SELECT COUNT(*) FROM media WHERE missing_since IS NOT NULL")
    final_missing = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(*) FROM media 
        WHERE is_duplicate = FALSE AND is_organized = TRUE
    """)
    visible = cursor.fetchone()[0]
    
    print(f"\n📈 Status final:")
    print(f"   Missing: {final_missing}")
    print(f"   Visíveis: {visible}")
    
    conn.close()

if __name__ == "__main__":
    fast_recover_wsl_mount()
