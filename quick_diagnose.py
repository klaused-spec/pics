#!/usr/bin/env python3
"""Quick database diagnostic"""
import os
import sys
os.chdir(os.path.join(os.path.dirname(__file__), "backend"))
sys.path.insert(0, os.getcwd())

from sqlalchemy.orm import sessionmaker
from app.core.database import engine
from app.models import Media

SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

total = db.query(Media).count()
non_dup = db.query(Media).filter(Media.is_duplicate == False).count()
duplicates = db.query(Media).filter(Media.is_duplicate == True).count()
missing = db.query(Media).filter(Media.missing_since.isnot(None)).count()
not_organized = db.query(Media).filter(Media.is_organized == False).count()

print(f"Total no banco: {total}")
print(f"Visíveis (não-duplicatas): {non_dup}")
print(f"Duplicatas: {duplicates}")
print(f"Missing (deletados): {missing}")
print(f"Não organizados: {not_organized}")
print(f"\n💡 Se você tinha 83k e agora vê 73k na galeria:")
print(f"   A diferença é de {83000 - non_dup} fotos")
print(f"   Possíveis causas:")
print(f"   - {duplicates} foram marcadas como duplicata")
print(f"   - {missing} foram marcadas como missing")
print(f"   - {not_organized} não estão organizadas")

db.close()
