#!/usr/bin/env python3
"""
Recover files marked as missing if they're actually accessible now.
Useful after reconnecting a stale mount (e.g., WSL /mnt/g).
"""
import os
import sys
os.chdir(os.path.join(os.path.dirname(__file__), "backend"))
sys.path.insert(0, os.getcwd())

from sqlalchemy.orm import sessionmaker
from app.core.database import engine
from app.core.config import settings
from app.models import Media
import datetime

SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

def check_and_recover_missing():
    """
    Verifica arquivos marcados como missing e tenta recuperá-los.
    Se conseguir encontrar o arquivo no disco, remove a flag de missing.
    """
    # Busca todos os missing
    missing_media = db.query(Media).filter(Media.missing_since.isnot(None)).all()
    
    print(f"📂 Verificando {len(missing_media)} arquivos marcados como missing...")
    
    recovered = 0
    still_missing = 0
    still_stale = []
    
    for media in missing_media:
        # Tenta encontrar o arquivo nos library_folders
        all_library_dirs = [settings.organized_dir] + settings.library_folders
        found = False
        
        for lib_dir in all_library_dirs:
            if not os.path.exists(lib_dir):
                still_stale.append(lib_dir)
                continue
                
            # Busca o arquivo
            for root, _dirs, files in os.walk(lib_dir):
                if media.filename in files:
                    filepath = os.path.join(root, media.filename)
                    # Tenta acessar
                    try:
                        if os.path.exists(filepath):
                            # Achou! Remove a flag de missing
                            media.missing_since = None
                            media.organized_path = filepath
                            recovered += 1
                            found = True
                            print(f"✓ Recuperado: {media.filename}")
                            break
                    except:
                        pass
            
            if found:
                break
        
        if not found:
            still_missing += 1
            print(f"✗ Ainda missing: {media.filename}")
    
    db.commit()
    
    print(f"\n📊 RESULTADO:")
    print(f"  ✓ Recuperados: {recovered}")
    print(f"  ✗ Ainda missing: {still_missing}")
    if still_stale:
        print(f"  ⚠ Pastas stale/inacessíveis:")
        for folder in set(still_stale):
            print(f"    - {folder}")
    
    print(f"\n💡 Total no banco agora: {db.query(Media).count()}")
    print(f"   Visíveis: {db.query(Media).filter(Media.is_duplicate == False, Media.is_organized == True).count()}")

db.close()

if __name__ == "__main__":
    check_and_recover_missing()
