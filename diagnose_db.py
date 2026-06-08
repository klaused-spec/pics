#!/usr/bin/env python3
"""
Script para diagnóstico do banco de dados de fotos.
Identifica inconsistências e ajuda a recuperar fotos faltantes.
"""
import os
import sys

# Ensure we're using the backend venv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
os.chdir(os.path.join(os.path.dirname(__file__), "backend"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models import Media, Face, Person
import sqlite3

def analyze_database():
    """Analisa o banco para encontrar inconsistências."""
    
    # Conecta ao banco
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    print("🔍 DIAGNÓSTICO DO BANCO DE DADOS\n")
    print("=" * 60)
    
    # 1. Contagem total
    total = db.query(Media).count()
    non_dup = db.query(Media).filter(Media.is_duplicate == False).count()
    duplicates = db.query(Media).filter(Media.is_duplicate == True).count()
    organized = db.query(Media).filter(Media.is_organized == True).count()
    not_organized = db.query(Media).filter(Media.is_organized == False).count()
    missing = db.query(Media).filter(Media.missing_since.isnot(None)).count()
    visible = db.query(Media).filter(
        Media.is_duplicate == False,
        Media.is_organized == True
    ).count()
    
    print(f"\n📊 CONTAGEM DE MÍDIA:")
    print(f"  Total no banco:           {total:>6}")
    print(f"  ├─ Não-duplicatas:        {non_dup:>6}")
    print(f"  ├─ Duplicatas:            {duplicates:>6}")
    print(f"  Organizadas:              {organized:>6}")
    print(f"  Não organizadas:          {not_organized:>6}")
    print(f"  Marcadas como missing:    {missing:>6}")
    print(f"  ✅ VISÍVEIS (na galeria):  {visible:>6}")
    
    # 2. Analisa duplicatas
    print(f"\n🔗 ANÁLISE DE DUPLICATAS:")
    
    # Encontra grupos de duplicatas (mesmo arquivo duplicado)
    dup_groups = {}
    duplicates_media = db.query(Media).filter(Media.is_duplicate == True).all()
    
    for dup in duplicates_media:
        if dup.duplicate_of_id not in dup_groups:
            dup_groups[dup.duplicate_of_id] = 0
        dup_groups[dup.duplicate_of_id] += 1
    
    if dup_groups:
        print(f"  Total de arquivos-origem com duplicatas: {len(dup_groups)}")
        max_copies = max(dup_groups.values()) if dup_groups else 0
        print(f"  Máximo de cópias do mesmo arquivo: {max_copies}")
    else:
        print(f"  Nenhuma duplicata detectada.")
    
    # 3. Verifica faces órfãs
    print(f"\n👤 ANÁLISE DE ROSTOS:")
    all_faces = db.query(Face).all()
    orphan_faces = [f for f in all_faces if not f.media_items]
    confirmed_faces = db.query(Face).filter(Face.is_confirmed == True).count()
    unconfirmed_faces = db.query(Face).filter(Face.is_confirmed == False).count()
    
    print(f"  Total de rostos: {len(all_faces)}")
    print(f"  ├─ Confirmados: {confirmed_faces}")
    print(f"  ├─ Não confirmados: {unconfirmed_faces}")
    print(f"  ├─ Órfãos (sem mídia): {len(orphan_faces)}")
    
    # 4. Analisa não organizados
    print(f"\n📁 ARQUIVOS NÃO ORGANIZADOS ({not_organized}):")
    if not_organized > 0:
        not_org_media = db.query(Media).filter(Media.is_organized == False).limit(10).all()
        for m in not_org_media:
            status = "dup" if m.is_duplicate else "orig"
            print(f"  - {m.filename[:40]:40} ({status})")
        if not_organized > 10:
            print(f"  ... e mais {not_organized - 10}")
    
    # 5. Análise de desaparecimento
    print(f"\n⚠️  ANÁLISE DO DESAPARECIMENTO (83k → 73k):")
    print(f"  Diferença reportada: ~10.000 arquivos")
    print(f"  Possíveis causas:")
    print(f"    1. Marcados como duplicata (incorretamente): {duplicates}")
    print(f"    2. Não organizados: {not_organized}")
    print(f"    3. Marcados como missing: {missing}")
    print(f"    4. Deletados do DB: {total - organized}")
    
    unaccounted = 83000 - visible
    if unaccounted > 0:
        print(f"\n  ❌ Não visíveis na galeria: {unaccounted}")
    
    # 6. Verifica integridade de paths
    print(f"\n🔗 INTEGRIDADE DE PATHS:")
    missing_paths = db.query(Media).filter(
        Media.is_organized == True,
        Media.organized_path == None
    ).count()
    invalid_paths = 0
    
    all_organized = db.query(Media).filter(Media.is_organized == True).limit(100).all()
    for m in all_organized:
        if m.organized_path and not os.path.exists(m.organized_path):
            invalid_paths += 1
    
    print(f"  Paths nulos: {missing_paths}")
    print(f"  Paths que não existem no disco: {invalid_paths}/100 (amostra)")
    
    print("\n" + "=" * 60)
    
    # 7. Recomendações
    print(f"\n💡 RECOMENDAÇÕES:")
    if duplicates > 5000:
        print(f"  1. ⚠️  Muitos duplicados ({duplicates}) - verifique se é correto")
    if not_organized > 1000:
        print(f"  2. ⚠️  Muitos não organizados ({not_organized}) - execute SCAN")
    if orphan_faces > 100:
        print(f"  3. 🗑️  {orphan_faces} rostos órfãos - execute PURGE")
    if missing > 0:
        print(f"  4. 🗑️  {missing} arquivos missing - clique PURGE-MISSING para remover")
    
    print(f"\n  5. Execute: /api/jobs/audit - para auditoria completa")
    print(f"  6. Execute: /api/jobs/sync - para sincronizar com disco")
    
    db.close()

if __name__ == "__main__":
    try:
        analyze_database()
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
