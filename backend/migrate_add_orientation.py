"""
Migration: preenche display_rotation para todos os registros existentes no banco
que ainda estão com o valor padrão 0 (ou seja, nunca foram preenchidos automaticamente).

Uso:
    cd backend
    python migrate_add_orientation.py
    python migrate_add_orientation.py --workers 8

Flags opcionais:
    --dry-run      Mostra o que seria atualizado sem gravar
    --batch N      Tamanho do batch por worker (padrão 500)
    --workers N    Threads paralelas de leitura de arquivo (padrão 4)
    --force        Atualiza mesmo registros que já têm display_rotation != 0
"""
import sys
import os
import argparse
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Permite rodar diretamente sem instalar o pacote
sys.path.insert(0, os.path.dirname(__file__))

from app.core.database import SessionLocal
from app.models import Media
from app.services.organizer import get_video_metadata, get_image_orientation


def get_orientation_for_file(filepath: str, media_type: str) -> int:
    """Retorna o display_rotation correto lendo o arquivo no disco."""
    try:
        if not filepath or not os.path.exists(filepath):
            return 0
        if media_type == "image":
            return get_image_orientation(filepath)
        elif media_type == "video":
            meta = get_video_metadata(filepath)
            return meta.get("rotation", 0)
    except Exception as e:
        logger.debug(f"Erro ao ler orientação de {filepath}: {e}")
    return 0


def _process_row(row: tuple) -> tuple:
    """Processa um único registro fora do DB: (id, filepath, media_type) -> (id, rotation, error)."""
    media_id, filepath, media_type = row
    try:
        rotation = get_orientation_for_file(filepath, media_type)
        return (media_id, rotation, None)
    except Exception as e:
        return (media_id, 0, str(e))


def run(dry_run: bool = False, batch_size: int = 500, force: bool = False, workers: int = 4):
    db = SessionLocal()
    try:
        query = db.query(Media.id, Media.organized_path, Media.media_type).filter(
            Media.is_duplicate == False,
            Media.organized_path.isnot(None),
        )
        if not force:
            query = query.filter(Media.display_rotation == 0)

        total = query.count()
        logger.info(f"Total de registros a processar: {total} (workers={workers}, dry_run={dry_run}, force={force})")

        updated = 0
        skipped = 0
        errors = 0
        offset = 0
        t0 = time.monotonic()

        while True:
            rows = query.order_by(Media.id).offset(offset).limit(batch_size).all()
            if not rows:
                break

            # Leitura de arquivo em paralelo (I/O-bound)
            results = {}
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(_process_row, row): row for row in rows}
                for future in as_completed(futures):
                    media_id, rotation, err = future.result()
                    if err:
                        errors += 1
                    else:
                        results[media_id] = rotation

            # Gravação no DB (single-thread, SQLite não suporta writes concorrentes)
            if not dry_run and results:
                for media_id, rotation in results.items():
                    db.query(Media).filter(Media.id == media_id).update(
                        {Media.display_rotation: rotation},
                        synchronize_session=False,
                    )
                    updated += 1
                db.commit()
            else:
                updated += len(results)

            offset += batch_size

            elapsed = time.monotonic() - t0
            rate = updated / elapsed if elapsed > 0 else 0
            eta = (total - updated) / rate if rate > 0 else 0
            logger.info(f"  {updated}/{total} ({100*updated//total}%) — {rate:.0f}/s — ETA {eta:.0f}s")

        elapsed = time.monotonic() - t0
        logger.info(f"Concluído: {updated} atualizados, {skipped} já corretos, {errors} erros em {elapsed:.1f}s")
        if dry_run:
            logger.info("(dry-run: nenhuma alteração foi gravada)")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Preenche display_rotation no banco a partir dos metadados dos arquivos")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem gravar")
    parser.add_argument("--batch", type=int, default=500, help="Tamanho do batch por ciclo (padrão 500)")
    parser.add_argument("--workers", type=int, default=4, help="Threads paralelas de leitura (padrão 4)")
    parser.add_argument("--force", action="store_true", help="Sobrescreve mesmo registros com rotation != 0")
    args = parser.parse_args()
    run(dry_run=args.dry_run, batch_size=args.batch, force=args.force, workers=args.workers)
