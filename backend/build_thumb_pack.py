"""Gera um PACOTE OFFLINE de thumbnails (um único .zip) para importar no app.

Fluxo pretendido:
  1. Rode este script no PC (onde estão os thumbs e o pics.db).
  2. Copie o .zip gerado para um pendrive.
  3. No app Android: Configurações > Biblioteca > "Importar pacote offline",
     escolha o .zip. O app extrai tudo para a pasta local de thumbs E carrega
     a lista de metadados (items.json), eliminando o sync longo na carga inicial.

O pacote contém:
  - {id}.jpg    thumbnail de cada mídia (nome = id, bate com THUMB_DIR/{id}.jpg).
  - items.json  lista completa de metadados (id, filename, date_taken, etc.).
  - manifest.json  metadados leves do pacote {version, size, count, created_at}.

Uso:
  python build_thumb_pack.py [--out CAMINHO.zip] [--size 300] [--all]

  --size   tamanho preferido do thumb (default 300). Igual ao usado no app.
  --all    inclui TODOS os thumbs do cache (ignora o filtro do banco).
           Por padrão inclui só mídias elegíveis (is_duplicate=0 e
           is_organized=1), que são as que aparecem no app.
"""
import argparse
import json
import os
import sys
import time
import zipfile

# Permite importar o app (settings/DB) rodando de dentro de backend/.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings  # noqa: E402


def thumb_cache_dir() -> str:
    return os.path.join(settings.organized_dir, ".thumbnails", "images")


def build_thumb_index(size: int) -> dict[str, str]:
    """id -> caminho, lendo o diretório UMA vez.

    Convivem dois padrões de nome: {id}_{size}.jpg (preferido) e {id}_{nome}.jpg.
    (Mesma lógica de backend/app/api/media.py.)
    """
    cache_dir = thumb_cache_dir()
    index: dict[str, str] = {}
    preferred_suffix = f"_{size}.jpg"
    try:
        with os.scandir(cache_dir) as it:
            for entry in it:
                name = entry.name
                if not name.endswith(".jpg"):
                    continue
                prefix = name.split("_", 1)[0]
                if prefix not in index or name.endswith(preferred_suffix):
                    index[prefix] = entry.path
    except FileNotFoundError:
        print(f"ERRO: pasta de thumbs nao encontrada: {cache_dir}")
        sys.exit(1)
    return index


def eligible_ids() -> set[str] | None:
    """Ids elegiveis (is_duplicate=0 e is_organized=1). None se falhar o DB."""
    try:
        from app.core.database import SessionLocal
        from app.models.models import Media
        db = SessionLocal()
        try:
            rows = (
                db.query(Media.id)
                .filter(Media.is_duplicate == False, Media.is_organized == True)  # noqa: E712
                .all()
            )
            return {str(r[0]) for r in rows}
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover
        print(f"AVISO: nao consegui ler o banco ({exc}); usando TODOS os thumbs.")
        return None


def build_items_json(eligible: set[str] | None) -> str:
    """Gera items.json com metadados de todas as midias elegiveis.

    Retorna string JSON pronta para gravar no zip. Inclui apenas os campos
    que o app usa na galeria (mesmo formato do /media/sync/manifest).
    """
    try:
        from app.core.database import SessionLocal
        from app.models.models import Media
        import os
        db = SessionLocal()
        try:
            query = db.query(Media).filter(
                Media.is_duplicate == False, Media.is_organized == True  # noqa: E712
            )
            items = []
            for media in query.yield_per(500):
                mid = str(media.id)
                if eligible is not None and mid not in eligible:
                    continue
                filepath = media.organized_path or media.original_path or ""
                folder = os.path.dirname(os.path.normpath(filepath)) if filepath else None
                items.append({
                    "id": media.id,
                    "filename": media.filename,
                    "media_type": media.media_type,
                    "mime_type": media.mime_type,
                    "date_taken": media.date_taken.isoformat() if media.date_taken else None,
                    "year": media.date_taken.year if media.date_taken else None,
                    "month": media.date_tja fiz , nada
                    aken.month if media.date_taken else None,
                    "duration_seconds": media.duration_seconds,
                    "sha256_hash": media.sha256_hash,
                    "folder": folder,
                    # URLs preenchidas pelo app com o baseUrl configurado pelo usuario.
                    # Gravamos None aqui; o app substitui na importacao.
                    "thumbnail_url": None,
                    "file_url": None,
                    "stream_url": None,
                    "local_thumbnail_uri": None,
                    "thumbnail_failed": False,
                })
            return json.dumps(items, separators=(',', ':'))
        finally:
            db.close()
    except Exception as exc:
        print(f"AVISO: nao consegui gerar items.json ({exc}); pacote so tera thumbs.")
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera pacote offline de thumbnails.")
    parser.add_argument("--out", default=None, help="Caminho do .zip de saida.")
    parser.add_argument("--size", type=int, default=300, help="Tamanho preferido (px).")
    parser.add_argument("--all", action="store_true", help="Inclui todos os thumbs do cache.")
    args = parser.parse_args()

    out_path = args.out or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"thumb-pack-{args.size}.zip",
    )

    t0 = time.time()
    print(f"Lendo cache de thumbs (size preferido={args.size})...")
    index = build_thumb_index(args.size)
    print(f"  {len(index)} thumbnails no cache.")

    if not args.all:
        ids = eligible_ids()
        if ids is not None:
            before = len(index)
            index = {k: v for k, v in index.items() if k in ids}
            print(f"  Filtrado por midias elegiveis: {before} -> {len(index)}.")

    if not index:
        print("Nada para empacotar. Rode o warmup de thumbs no backend primeiro.")
        sys.exit(1)

    # Gera items.json antes de abrir o zip (pode demorar para DBs grandes).
    eligible_set = None if args.all else eligible_ids()
    print("Gerando items.json com metadados das midias...")
    items_json = build_items_json(eligible_set)
    if items_json:
        import json as _json
        n_items = len(_json.loads(items_json))
        print(f"  {n_items} itens no items.json.")
    else:
        print("  items.json nao gerado (banco indisponivel); o app precisara sincronizar.")

    # ZIP_STORED: thumbs ja sao JPG comprimidos; recomprimir so gasta CPU/tempo.
    included: list[int] = []
    print(f"Gravando {out_path} ...")
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for prefix, path in index.items():
            try:
                mid = int(prefix)
            except ValueError:
                continue
            try:
                zf.write(path, arcname=f"{mid}.jpg")
                included.append(mid)
            except OSError:
                continue

        if items_json:
            zf.writestr("items.json", items_json)

        manifest = {
            "version": 2,
            "size": args.size,
            "count": len(included),
            "has_items": bool(items_json),
            "created_at": int(time.time()),
        }
        zf.writestr("manifest.json", json.dumps(manifest))

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    dt = time.time() - t0
    print(
        f"OK: {len(included)} thumbnails, {size_mb:.1f} MB em {dt:.1f}s\n"
        f"  -> {out_path}\n"
        f"Copie para o pendrive e importe em Configuracoes > Biblioteca > Importar pacote offline."
    )


if __name__ == "__main__":
    main()
