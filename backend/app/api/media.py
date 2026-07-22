"""
Endpoints de mídia: listagem, busca, detalhes, thumbnail, streaming.
"""
import datetime
import os
import mimetypes
from pathlib import Path
from typing import Optional

from PIL import Image
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user
from app.models import Media, Tag, Person, Face
from app.services.ai_vision import search_by_description
from app.services.file_ops import media_file_operation_lock

router = APIRouter(prefix="/media", tags=["media"])


# --- Índice do cache de thumbnails (id -> caminho no disco) ---------------
# Construído com UM único os.scandir e reutilizado entre requests. Evita o
# custo catastrófico de globbar/escanear a pasta (dezenas de milhares de
# arquivos, em disco lento) uma vez por lote — ou pior, uma vez por id
# inexistente. Invalidado por tempo (TTL) e quando o nº de arquivos muda.
_THUMB_INDEX: dict[str, str] = {}
_THUMB_INDEX_BUILT_AT: float = 0.0
_THUMB_INDEX_TTL = 300.0  # 5 min
_THUMB_INDEX_SIZE = None  # size (px) para o qual o índice foi montado


def _thumb_cache_dir() -> str:
    return os.path.join(settings.organized_dir, ".thumbnails", "images")


def _build_thumb_index(size: int) -> dict[str, str]:
    """Monta id -> caminho lendo o diretório UMA vez.

    Convivem dois padrões: {id}_{size}.jpg (preferido) e {id}_{nome}.jpg.
    """
    cache_dir = _thumb_cache_dir()
    index: dict[str, str] = {}
    preferred_suffix = f"_{size}.jpg"
    try:
        with os.scandir(cache_dir) as it:
            for entry in it:
                name = entry.name
                if not name.endswith(".jpg"):
                    continue
                prefix = name.split("_", 1)[0]
                # Prioriza "{id}_{size}.jpg"; senão fica com o primeiro que achar.
                if prefix not in index or name.endswith(preferred_suffix):
                    index[prefix] = entry.path
    except FileNotFoundError:
        pass
    return index


def _get_thumb_index(size: int) -> dict[str, str]:
    """Retorna o índice, reconstruindo se expirou o TTL ou mudou o size."""
    import time
    global _THUMB_INDEX, _THUMB_INDEX_BUILT_AT, _THUMB_INDEX_SIZE
    now = time.monotonic()
    if (
        not _THUMB_INDEX
        or _THUMB_INDEX_SIZE != size
        or now - _THUMB_INDEX_BUILT_AT > _THUMB_INDEX_TTL
    ):
        _THUMB_INDEX = _build_thumb_index(size)
        _THUMB_INDEX_BUILT_AT = now
        _THUMB_INDEX_SIZE = size
    return _THUMB_INDEX


def _is_in_library_folder(filepath: str) -> bool:
    """Verifica se o arquivo está em uma das library_folders (não em organized_dir)."""
    if not filepath:
        return False
    abs_path = os.path.abspath(filepath)
    abs_organized = os.path.abspath(settings.organized_dir)
    if abs_path.startswith(abs_organized + os.sep):
        return False
    for folder in settings.library_folders:
        abs_folder = os.path.abspath(folder)
        if abs_path.startswith(abs_folder + os.sep):
            return True
    return False


def _get_date_dir(year: int, month: int) -> str:
    """Retorna a pasta base padrão para um ano/mês."""
    if settings.organization_pattern == "year_month":
        return os.path.join(settings.organized_dir, f"{year}_{month:02d}")
    return os.path.join(settings.organized_dir, str(year), f"{month:02d}")


def _get_date_dir_candidates(year: int, month: int, base_dir: Optional[str] = None) -> list[str]:
    """Retorna possíveis diretórios de data para o mês/ano, considerando layouts comuns."""
    base_dir = base_dir or settings.organized_dir
    if settings.organization_pattern == "year_month":
        candidates = [
            os.path.join(base_dir, f"{year}_{month:02d}"),
            os.path.join(base_dir, str(year), f"{year}_{month:02d}"),
        ]
    else:
        candidates = [os.path.join(base_dir, str(year), f"{month:02d}")]

    return [os.path.normpath(path) for path in dict.fromkeys(candidates)]


def _get_month_prefixes(year: int, month: int) -> list[str]:
    """Retorna todos os prefixes de diretório possíveis para organized_dir e library_folders."""
    prefixes = _get_date_dir_candidates(year, month)
    for folder in settings.library_folders:
        prefixes.extend(_get_date_dir_candidates(year, month, folder))
    return [os.path.normpath(path) for path in dict.fromkeys(prefixes)]


def _find_date_dir_for_month(year: int, month: int) -> str:
    """Retorna o primeiro diretório de mês existente ou o diretório padrão."""
    for candidate in _get_month_prefixes(year, month):
        if os.path.isdir(candidate):
            return candidate
    return _get_date_dir(year, month)


def _get_folder_counts_for_date_dir(db: Session, date_dir: str) -> dict[str, int]:
    """Conta arquivos em subpastas do diretório de mês usando uma única consulta SQL."""
    if not os.path.isdir(date_dir):
        return {}

    normalized_dir = os.path.normpath(date_dir).rstrip(os.sep) + os.sep
    relative_path = func.substr(Media.organized_path, len(normalized_dir) + 1)
    folder_name = func.substr(relative_path, 1, func.instr(relative_path, os.sep) - 1)

    results = (
        db.query(folder_name.label('folder'), func.count(Media.id).label('count'))
        .filter(Media.organized_path.like(f"{normalized_dir}%"))
        .filter(Media.organized_path.like(f"{normalized_dir}%{os.sep}%"))
        .group_by(folder_name)
        .all()
    )

    return {folder: count for folder, count in results if folder}


def _normalize_path_for_match(path: str) -> str:
    return os.path.normpath(path).replace('\\', '/').rstrip('/')


def _folder_counts_by_month(db: Session, media_type: Optional[str] = None) -> dict[tuple[int, int], dict[str, int]]:
    """Conta subpastas de todos os meses em uma passada para montar a timeline rápido."""
    query = db.query(Media.date_taken, Media.organized_path).filter(
        Media.is_organized == True,
        Media.date_taken.isnot(None),
        Media.organized_path.isnot(None),
    )
    if media_type:
        query = query.filter(Media.media_type == media_type)

    prefix_cache: dict[tuple[int, int], list[str]] = {}
    folder_counts: dict[tuple[int, int], dict[str, int]] = {}

    for date_taken, organized_path in query.yield_per(1000):
        month_key = (date_taken.year, date_taken.month)
        prefixes = prefix_cache.get(month_key)
        if prefixes is None:
            prefixes = [_normalize_path_for_match(prefix) + '/' for prefix in _get_month_prefixes(*month_key)]
            prefix_cache[month_key] = prefixes

        normalized_path = _normalize_path_for_match(organized_path)
        for prefix in prefixes:
            if not normalized_path.startswith(prefix):
                continue

            relative_path = normalized_path[len(prefix):]
            if '/' not in relative_path:
                break

            folder_name = relative_path.split('/', 1)[0]
            counts = folder_counts.setdefault(month_key, {})
            counts[folder_name] = counts.get(folder_name, 0) + 1
            break

    return folder_counts


def _sanitize_folder_name(folder_name: str) -> str:
    """Sanitiza o nome da pasta para evitar traversal e segmentos inválidos."""
    folder_name = folder_name.strip()
    if not folder_name:
        raise HTTPException(status_code=400, detail="Nome de pasta inválido")

    segments = [segment.strip() for segment in folder_name.replace('\\', '/').split('/') if segment.strip()]
    if not segments or any(segment in ('.', '..') for segment in segments):
        raise HTTPException(status_code=400, detail="Nome de pasta inválido")

    return os.path.join(*segments)


class FolderMoveRequest(BaseModel):
    year: int
    month: int
    folder_name: str
    media_ids: list[int] = []


class BulkDateCorrectionRequest(BaseModel):
    date_taken: datetime.datetime
    media_ids: list[int] = []
    source_year: Optional[int] = None
    source_month: Optional[int] = None
    source_folder: Optional[str] = None
    write_metadata: bool = True
    move_files: bool = True
    keep_folder: bool = True
    rename_videos: bool = True


def _write_jpeg_exif_date(filepath: str, date_taken: datetime.datetime) -> bool:
    """Atualiza datas EXIF principais em JPEG quando Pillow consegue preservar o EXIF."""
    if Path(filepath).suffix.lower() not in (".jpg", ".jpeg"):
        return False

    exif_date = date_taken.strftime("%Y:%m:%d %H:%M:%S")
    with Image.open(filepath) as image:
        exif = image.getexif()
        exif[306] = exif_date  # Image DateTime
        exif[36867] = exif_date  # DateTimeOriginal
        exif[36868] = exif_date  # DateTimeDigitized
        image.save(filepath, exif=exif)
    return True


def _resolve_media_path(media: Media) -> str:
    return media.organized_path or media.original_path


def _build_unique_destination(source_path: str, destination_dir: str, filename: Optional[str] = None) -> str:
    os.makedirs(destination_dir, exist_ok=True)
    filename = filename or os.path.basename(source_path)
    dest_path = os.path.join(destination_dir, filename)
    if not os.path.exists(dest_path):
        return dest_path

    base = Path(filename).stem
    ext = Path(filename).suffix
    counter = 1
    while os.path.exists(dest_path):
        dest_path = os.path.join(destination_dir, f"{base}_{counter}{ext}")
        counter += 1
    return dest_path


def _build_date_prefixed_filename(filepath: str, date_taken: datetime.datetime) -> str:
    original = Path(filepath).name
    prefix = date_taken.strftime("%Y-%m-%d_%H%M%S")
    if original.startswith(prefix + "_"):
        return original
    return f"{prefix}_{original}"


def _get_relative_folder_under_month(filepath: str, year: int, month: int) -> Optional[str]:
    normalized_path = _normalize_path_for_match(filepath)
    for prefix in _get_month_prefixes(year, month):
        normalized_prefix = _normalize_path_for_match(prefix) + '/'
        if not normalized_path.startswith(normalized_prefix):
            continue
        relative_path = normalized_path[len(normalized_prefix):]
        if '/' not in relative_path:
            return None
        folder_part = relative_path.rsplit('/', 1)[0]
        return _sanitize_folder_name(folder_part)
    return None


@router.get("/")
def list_media(
    current_user: dict = Depends(get_current_user),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    media_type: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    day: Optional[int] = None,
    folder: Optional[str] = None,
    person_id: Optional[int] = None,
    tag: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Lista mídias com paginação e filtros."""
    query = db.query(Media).filter(Media.is_organized == True)

    if media_type:
        query = query.filter(Media.media_type == media_type)

    if year:
        query = query.filter(func.extract("year", Media.date_taken) == year)
    if month:
        query = query.filter(func.extract("month", Media.date_taken) == month)
    if day:
        query = query.filter(func.extract("day", Media.date_taken) == day)

    if folder:
        if not year or not month:
            raise HTTPException(status_code=400, detail="Filtrar por pasta requer ano e mês")
        safe_folder = _sanitize_folder_name(folder)

        folder_paths = []
        for date_dir in _get_date_dir_candidates(year, month):
            folder_paths.append(os.path.join(date_dir, safe_folder))
        for lib in settings.library_folders:
            for date_dir in _get_date_dir_candidates(year, month, lib):
                folder_paths.append(os.path.join(date_dir, safe_folder))

        conditions = [Media.organized_path.like(f"{path}{os.sep}%") for path in folder_paths]
        if conditions:
            query = query.filter(or_(*conditions))
    elif year and month:
        query = query.filter(Media.is_duplicate == False)
        # Sem folder específico: mostra apenas arquivos na raiz do mês (não em subpastas).
        prefixes = _get_month_prefixes(year, month)

        conditions = []
        for p in prefixes:
            prefix = p.rstrip(os.sep) + os.sep
            conditions.append(
                and_(
                    Media.organized_path.like(f"{prefix}%"),
                    ~Media.organized_path.like(f"{prefix}%{os.sep}%"),
                )
            )

        if conditions:
            query = query.filter(or_(*conditions))
    else:
        query = query.filter(Media.is_duplicate == False)

    if person_id:
        query = query.join(Media.faces).filter(Face.person_id == person_id)

    if tag:
        query = query.join(Media.tags).filter(Tag.name == tag.lower())

    total = query.count()
    items = (
        query.order_by(Media.date_taken.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "items": [_media_to_dict(m) for m in items],
    }


@router.get("/search")
def search_media(
    current_user: dict = Depends(get_current_user),
    q: str = Query(..., min_length=2),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Busca mídias por texto livre (descrição IA, local, tags)."""
    results = search_by_description(q, db, limit=limit)
    return {
        "query": q,
        "total": len(results),
        "items": [_media_to_dict(m) for m in results],
    }


@router.get("/timeline")
def get_timeline(
    current_user: dict = Depends(get_current_user),
    media_type: Optional[str] = None,
    include_folders: bool = Query(True),
    db: Session = Depends(get_db),
):
    """Retorna timeline agrupada por ano/mês."""
    q = (
        db.query(
            func.extract("year", Media.date_taken).label("year"),
            func.extract("month", Media.date_taken).label("month"),
            func.count(Media.id).label("count"),
        )
        .filter(Media.is_duplicate == False, Media.is_organized == True)
    )
    if media_type:
        q = q.filter(Media.media_type == media_type)
    results = (
        q.group_by("year", "month")
        .order_by(func.extract("year", Media.date_taken).desc(), func.extract("month", Media.date_taken).desc())
        .all()
    )

    folder_counts_by_month = _folder_counts_by_month(db, media_type) if include_folders else {}
    timeline = []
    for r in results:
        if r.year is None:
            continue
        year = int(r.year)
        month = int(r.month)
        folder_map = folder_counts_by_month.get((year, month), {})

        folders = [{"name": name, "count": cnt} for name, cnt in sorted(folder_map.items())]

        timeline.append({"year": year, "month": month, "count": r.count, "folders": folders})

    return timeline


@router.get("/timeline/folders")
def get_timeline_folders(
    year: int = Query(..., ge=1900),
    month: int = Query(..., ge=1, le=12),
    media_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Retorna a lista de pastas para um mês/ano específico."""
    folder_map = {}
    try:
        for date_dir in _get_month_prefixes(year, month):
            counts = _get_folder_counts_for_date_dir(db, date_dir)
            for name, cnt in counts.items():
                folder_map[name] = folder_map.get(name, 0) + cnt
    except OSError:
        folder_map = {}

    return [{"name": name, "count": cnt} for name, cnt in sorted(folder_map.items())]


@router.post("/folders")
def create_folder_and_move_media(data: FolderMoveRequest, db: Session = Depends(get_db)):
    """Cria uma pasta dentro da data selecionada e move mídias para ela."""
    with media_file_operation_lock:
        date_dir = _find_date_dir_for_month(data.year, data.month)
        folder_path = _sanitize_folder_name(data.folder_name)
        destination_dir = os.path.join(date_dir, folder_path)
        os.makedirs(destination_dir, exist_ok=True)

        moved = 0
        errors = []
        for media_id in data.media_ids:
            media = db.query(Media).get(media_id)
            if not media:
                errors.append(f"Mídia {media_id} não encontrada")
                continue

            filepath = media.organized_path or media.original_path
            if not filepath or not os.path.exists(filepath):
                errors.append(f"Arquivo não encontrado para mídia {media_id}")
                continue

            if _is_in_library_folder(filepath) and not settings.allow_library_modify:
                errors.append(f"Modificação de arquivos em biblioteca não autorizada: {media.filename}")
                continue

            dest_path = os.path.join(destination_dir, os.path.basename(filepath))
            if os.path.exists(dest_path):
                base = Path(filepath).stem
                ext = Path(filepath).suffix
                counter = 1
                while os.path.exists(dest_path):
                    dest_path = os.path.join(destination_dir, f"{base}_{counter}{ext}")
                    counter += 1

            try:
                os.makedirs(destination_dir, exist_ok=True)
                os.replace(filepath, dest_path)
                media.original_path = dest_path
                media.organized_path = dest_path
                media.filename = os.path.basename(dest_path)
                media.is_organized = True
                moved += 1
            except Exception as exc:
                errors.append(f"Erro ao mover mídia {media_id}: {exc}")

        db.commit()
    if errors and moved == 0:
        raise HTTPException(status_code=400, detail={"moved": moved, "errors": errors})
    return {"status": "ok", "moved": moved, "errors": errors}


@router.post("/bulk-date-correction")
def bulk_date_correction(data: BulkDateCorrectionRequest, db: Session = Depends(get_db)):
    """Corrige data em lote, grava EXIF quando possível e move arquivos para o mês correto."""
    if not data.media_ids:
        raise HTTPException(status_code=400, detail="Selecione ao menos uma mídia")

    corrected = 0
    metadata_written = 0
    moved = 0
    errors = []

    target_date = data.date_taken.replace(tzinfo=None)
    target_date_dir = _get_date_dir(target_date.year, target_date.month)

    with media_file_operation_lock:
        for media_id in data.media_ids:
            media = db.query(Media).get(media_id)
            if not media:
                errors.append(f"Mídia {media_id} não encontrada")
                continue

            filepath = _resolve_media_path(media)
            if not filepath or not os.path.exists(filepath):
                errors.append(f"Arquivo não encontrado para mídia {media_id}")
                continue

            if _is_in_library_folder(filepath) and not settings.allow_library_modify:
                errors.append(f"Modificação de arquivos em biblioteca não autorizada: {media.filename}")
                continue

            if data.write_metadata and media.media_type == "image":
                try:
                    if _write_jpeg_exif_date(filepath, target_date):
                        metadata_written += 1
                except Exception as exc:
                    errors.append(f"Erro ao gravar EXIF em {media.filename}: {exc}")

            media.date_taken = target_date
            corrected += 1

            if data.move_files:
                destination_dir = target_date_dir
                if data.keep_folder:
                    folder_name = None
                    if data.source_folder:
                        folder_name = _sanitize_folder_name(data.source_folder)
                    elif data.source_year and data.source_month:
                        folder_name = _get_relative_folder_under_month(filepath, data.source_year, data.source_month)
                    if folder_name:
                        destination_dir = os.path.join(target_date_dir, folder_name)

                try:
                    destination_filename = None
                    if data.rename_videos and media.media_type == "video":
                        destination_filename = _build_date_prefixed_filename(filepath, target_date)

                    dest_path = _build_unique_destination(filepath, destination_dir, destination_filename)
                    os.replace(filepath, dest_path)
                    media.original_path = dest_path
                    media.organized_path = dest_path
                    media.filename = os.path.basename(dest_path)
                    media.is_organized = True
                    moved += 1
                except Exception as exc:
                    errors.append(f"Erro ao mover {media.filename}: {exc}")

        db.commit()
    return {
        "status": "ok",
        "corrected": corrected,
        "metadata_written": metadata_written,
        "moved": moved,
        "errors": errors,
    }


@router.get("/stats")
def get_stats(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retorna estatísticas gerais do acervo."""
    total = db.query(Media).filter(Media.is_duplicate == False).count()
    images = db.query(Media).filter(Media.media_type == "image", Media.is_duplicate == False).count()
    videos = db.query(Media).filter(Media.media_type == "video", Media.is_duplicate == False).count()
    duplicates = db.query(Media).filter(Media.is_duplicate == True).count()
    ai_processed = db.query(Media).filter(Media.ai_processed == True).count()
    persons = db.query(Person).count()
    faces = db.query(Face).count()
    missing = db.query(Media).filter(Media.missing_since.isnot(None)).count()

    return {
        "total_media": total,
        "images": images,
        "videos": videos,
        "duplicates_found": duplicates,
        "ai_processed": ai_processed,
        "persons": persons,
        "faces_detected": faces,
        "missing_files": missing,
    }


@router.get("/sync/manifest")
def get_sync_manifest(
    request: Request,
    current_user: dict = Depends(get_current_user),
    since: Optional[datetime.datetime] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(200, ge=1, le=1000),
    size: int = Query(300, ge=50, le=800),
    after_updated_at: Optional[datetime.datetime] = None,
    after_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Retorna manifesto incremental para clientes offline sincronizarem thumbnails.

    Suporta paginação por keyset (seek method): o cliente envia o cursor do
    último item recebido (`after_updated_at` + `after_id`) e o servidor devolve
    apenas os itens seguintes. Isso mantém cada página O(per_page) usando o
    índice composto (is_duplicate, is_organized, updated_at, id), evitando a
    degradação progressiva do OFFSET (páginas cada vez mais lentas).

    O parâmetro `page` é mantido apenas para compatibilidade/telemetria e não é
    usado para saltar linhas quando o cursor keyset está presente.
    """
    base_query = db.query(Media).filter(Media.is_duplicate == False, Media.is_organized == True)
    if since:
        base_query = base_query.filter(Media.updated_at > since)

    total = base_query.count()

    query = base_query
    use_keyset = after_updated_at is not None and after_id is not None
    if use_keyset:
        # (updated_at, id) > (after_updated_at, after_id) — comparação lexicográfica.
        query = query.filter(
            or_(
                Media.updated_at > after_updated_at,
                and_(Media.updated_at == after_updated_at, Media.id > after_id),
            )
        )

    ordered = query.order_by(Media.updated_at.asc(), Media.id.asc())
    if use_keyset:
        media_items = ordered.limit(per_page).all()
    else:
        # Primeira página (sem cursor) — offset é sempre 0 aqui.
        media_items = ordered.offset((page - 1) * per_page).limit(per_page).all()

    base_url = str(request.base_url).rstrip("/")
    server_time = datetime.datetime.utcnow()
    items = [_media_sync_item(media, base_url, size) for media in media_items]

    last = media_items[-1] if media_items else None
    next_cursor = None
    if last is not None:
        next_cursor = {
            "after_updated_at": (last.updated_at.isoformat() if last.updated_at else None),
            "after_id": last.id,
        }

    has_more = len(media_items) == per_page and (page * per_page < total or use_keyset)

    return {
        "server_time": server_time.isoformat(),
        "sync_token": server_time.isoformat(),
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "thumbnail_size": size,
        "items": items,
    }


@router.get("/{media_id}/thumbnail-cached")
def get_thumbnail_cached(media_id: int, size: int = Query(300, ge=50, le=800)):
    """Serve a thumbnail DIRETO do cache em disco, sem tocar o banco.

    Diferente de /thumbnail (que faz query no SQLite + valida mtime, e por isso
    serializa/trava sob concorrência quando o worker de AI/faces está gravando),
    este endpoint só lê o arquivo já cacheado (.thumbnails/images/{id}_{size}.jpg).
    Ideal para o sync em massa do app: sem lock de banco, alta concorrência.

    Se o cache não existir, retorna 404 — o app cai no fluxo /thumbnail normal
    (que regenera) como fallback.
    """
    cache_dir = os.path.join(settings.organized_dir, ".thumbnails", "images")
    cache_path = os.path.join(cache_dir, f"{media_id}_{size}.jpg")
    if not os.path.exists(cache_path):
        # Fallback: cache do organizer usa {id}_{nome_original}.jpg — procura por prefixo.
        import glob
        matches = glob.glob(os.path.join(cache_dir, f"{media_id}_*.jpg"))
        cache_path = matches[0] if matches else None
    if not cache_path or not os.path.exists(cache_path):
        raise HTTPException(status_code=404, detail="Thumbnail não está em cache")
    return FileResponse(
        cache_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=31536000"},
    )


class ThumbnailZipRequest(BaseModel):
    ids: list[int]


class ThumbnailHaveRequest(BaseModel):
    ids: list[int]


@router.post("/thumbnails/have")
def thumbnails_have(
    payload: ThumbnailHaveRequest,
    size: int = Query(300, ge=50, le=800),
    current_user: dict = Depends(get_current_user),
):
    """Dado um lote de ids, retorna QUAIS já têm thumbnail em cache no servidor.

    O app usa isso para baixar SÓ o que existe (via /thumbnails/zip) e pular os
    que ainda não foram gerados — o job de warmup preenche o resto em background
    e a navegação gera sob demanda. Usa o índice em memória (id -> caminho),
    então é O(len(ids)) sem tocar o disco por item.
    """
    ids = payload.ids or []
    if len(ids) > 5000:
        raise HTTPException(status_code=400, detail="Máximo de 5000 ids por consulta")
    index = _get_thumb_index(size)
    have = [i for i in ids if str(i) in index]
    return {"have": have}


@router.post("/thumbnails/zip")
def download_thumbnails_zip(
    payload: ThumbnailZipRequest,
    size: int = Query(300, ge=50, le=800),
    current_user: dict = Depends(get_current_user),
):
    """Empacota um LOTE de thumbnails já cacheadas num único ZIP.

    Em vez de o app fazer um request por imagem (110k round-trips, que o Caddy
    corta em HTTP/2), ele pede lotes de ids e recebe um ZIP só. Não regenera nem
    toca o banco. Cada entrada é "{id}.jpg". IDs sem cache são omitidos.
    """
    import io
    import zipfile

    ids = payload.ids or []
    if len(ids) > 2000:
        raise HTTPException(status_code=400, detail="Máximo de 2000 ids por lote")

    # Resolve os caminhos a partir de um índice em memória (id -> caminho),
    # montado com UM único scandir e reutilizado entre requests. Cada lote é
    # O(len(ids)) puro em memória — sem tocar o disco por id (antes: um glob por
    # id, e a maioria dos ~110k ids NÃO tem thumb em cache, então cada um varria
    # a pasta inteira -> horas). IDs sem cache são simplesmente omitidos.
    index = _get_thumb_index(size)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as zf:
        for media_id in ids:
            cache_path = index.get(str(media_id))
            if cache_path:
                try:
                    zf.write(cache_path, arcname=f"{media_id}.jpg")
                except Exception:
                    pass
    data = buffer.getvalue()

    return Response(
        content=data,
        media_type="application/zip",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/thumbnails/warmup")
def warmup_thumbnail_cache(
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    size: int = Query(300, ge=50, le=800),
    db: Session = Depends(get_db),
):
    """Pré-gera thumbnails em lote para melhorar performance da galeria."""
    import threading

    media_items = (
        db.query(Media)
        .filter(Media.is_duplicate == False, Media.is_organized == True)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    cache_dir = os.path.join(settings.organized_dir, ".thumbnails", "images")
    os.makedirs(cache_dir, exist_ok=True)

    generated = 0
    skipped = 0
    errors = []

    for media in media_items:
        cache_path = os.path.join(cache_dir, f"{media.id}_{size}.jpg")

        # Verifica se já existe
        if os.path.exists(cache_path):
            try:
                filepath = media.organized_path or media.original_path
                if os.path.exists(filepath):
                    source_mtime = os.path.getmtime(filepath)
                    cache_mtime = os.path.getmtime(cache_path)
                    if cache_mtime >= source_mtime:
                        skipped += 1
                        continue
            except Exception:
                pass

        try:
            filepath = media.organized_path or media.original_path
            if not os.path.exists(filepath):
                errors.append(f"{media.id}: arquivo não encontrado")
                continue

            if media.media_type == "image":
                from PIL import Image

                img = Image.open(filepath)
                img.thumbnail((size, size))
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(cache_path, format="JPEG", quality=80)
                generated += 1
            else:
                # Para vídeos, gera thumbnail
                from app.services.organizer import generate_video_thumbnail
                from PIL import Image

                thumb_tmp = cache_path + ".tmp"
                generate_video_thumbnail(filepath, thumb_tmp)

                if os.path.exists(thumb_tmp):
                    img = Image.open(thumb_tmp)
                    img.thumbnail((size, size))
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    img.save(cache_path, format="JPEG", quality=80)
                    os.unlink(thumb_tmp)
                    generated += 1
        except Exception as e:
            errors.append(f"{media.id}: {str(e)[:100]}")

    return {
        "status": "ok",
        "generated": generated,
        "skipped": skipped,
        "errors": errors,
        "page": page,
        "per_page": per_page,
        "page_count": len(media_items),
    }


@router.delete("/duplicates/all")
def delete_all_duplicates(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Move TODAS as duplicatas para .trash (mantém os originais).
    """
    import shutil

    dupes = db.query(Media).filter(
        Media.is_duplicate == True,
        Media.duplicate_of_id.isnot(None),
    ).all()

    deleted = 0
    errors = []
    for dupe in dupes:
        filepath = dupe.organized_path or dupe.original_path
        if not filepath:
            continue

        # Determinar trash_dir
        if _is_in_library_folder(filepath):
            if not settings.allow_library_modify:
                errors.append(f"{dupe.filename}: biblioteca protegida")
                continue
            abs_path = os.path.abspath(filepath)
            trash_dir = None
            for folder in settings.library_folders:
                abs_folder = os.path.abspath(folder)
                if abs_path.startswith(abs_folder + os.sep):
                    trash_dir = os.path.join(folder, ".trash")
                    break
            if not trash_dir:
                trash_dir = os.path.join(settings.organized_dir, ".trash")
        else:
            trash_dir = os.path.join(settings.organized_dir, ".trash")

        os.makedirs(trash_dir, exist_ok=True)
        trash_path = os.path.join(trash_dir, Path(filepath).name)

        if os.path.exists(trash_path):
            stem = Path(filepath).stem
            ext = Path(filepath).suffix
            i = 1
            while os.path.exists(trash_path):
                trash_path = os.path.join(trash_dir, f"{stem}_{i}{ext}")
                i += 1

        if os.path.exists(filepath):
            shutil.move(filepath, trash_path)

        for face in dupe.faces:
            db.delete(face)
        db.delete(dupe)
        deleted += 1

    db.commit()
    return {"status": "ok", "deleted": deleted, "errors": errors}


@router.get("/duplicates")
def get_duplicates(db: Session = Depends(get_db)):
    """
    Retorna grupos de duplicatas.
    Cada grupo contém o original + suas duplicatas para o usuário decidir qual manter.
    """
    # Busca todas as duplicatas que têm duplicate_of_id
    dupes = db.query(Media).filter(
        Media.is_duplicate == True,
        Media.duplicate_of_id.isnot(None),
    ).all()

    # Agrupa por original
    groups = {}
    for dupe in dupes:
        orig_id = dupe.duplicate_of_id
        if orig_id not in groups:
            original = db.query(Media).filter(Media.id == orig_id).first()
            if not original:
                continue
            groups[orig_id] = {
                "original": _media_summary(original),
                "duplicates": [],
            }
        groups[orig_id]["duplicates"].append(_media_summary(dupe))

    return list(groups.values())


def _media_summary(media: Media) -> dict:
    """Resumo compacto de uma mídia para listagem de duplicatas."""
    return {
        "id": media.id,
        "filename": media.filename,
        "organized_path": media.organized_path or media.original_path,
        "media_type": media.media_type,
        "date_taken": media.date_taken.isoformat() if media.date_taken else None,
        "width": media.width,
        "height": media.height,
        "is_duplicate": media.is_duplicate,
    }


def _media_sync_item(media: Media, base_url: str, thumbnail_size: int) -> dict:
    filepath = media.organized_path or media.original_path or ""
    folder = None
    if filepath:
        folder = os.path.dirname(os.path.normpath(filepath))

    return {
        "id": media.id,
        "filename": media.filename,
        "media_type": media.media_type,
        "mime_type": media.mime_type,
        "date_taken": media.date_taken.isoformat() if media.date_taken else None,
        "year": media.date_taken.year if media.date_taken else None,
        "month": media.date_taken.month if media.date_taken else None,
        "width": media.width,
        "height": media.height,
        "duration_seconds": media.duration_seconds,
        "updated_at": media.updated_at.isoformat() if media.updated_at else None,
        "sha256_hash": media.sha256_hash,
        "ai_description": media.ai_description,
        "ai_location": media.ai_location,
        "ai_scene_type": media.ai_scene_type,
        "ai_objects": media.ai_objects or [],
        "folder": folder,
        "thumbnail_url": f"{base_url}/api/media/{media.id}/thumbnail?size={thumbnail_size}",
        "file_url": f"{base_url}/api/media/{media.id}/file",
        "stream_url": f"{base_url}/api/media/{media.id}/stream" if media.media_type == "video" else None,
    }


@router.get("/{media_id}")
def get_media(
    media_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retorna detalhes de uma mídia."""
    media = db.query(Media).get(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Mídia não encontrada")
    return _media_to_dict(media, include_details=True)


@router.get("/{media_id}/neighbors")
def get_media_neighbors(media_id: int, db: Session = Depends(get_db)):
    """Retorna IDs da mídia anterior e próxima (por data)."""
    media = db.query(Media).get(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Mídia não encontrada")

    base = db.query(Media).filter(Media.is_duplicate == False, Media.is_organized == True)

    prev_media = (
        base.filter(Media.date_taken > media.date_taken)
        .order_by(Media.date_taken.asc())
        .first()
    )
    # Se não achou por data maior, pode ser mesmo timestamp - usa ID
    if not prev_media:
        prev_media = base.filter(Media.id < media.id).order_by(Media.id.desc()).first()

    next_media = (
        base.filter(Media.date_taken < media.date_taken)
        .order_by(Media.date_taken.desc())
        .first()
    )
    if not next_media:
        next_media = base.filter(Media.id > media.id).order_by(Media.id.asc()).first()

    return {
        "prev_id": prev_media.id if prev_media else None,
        "next_id": next_media.id if next_media else None,
    }


@router.get("/{media_id}/file")
def get_media_file(media_id: int, db: Session = Depends(get_db)):
    """Retorna o arquivo da mídia."""
    media = db.query(Media).get(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Mídia não encontrada")

    filepath = media.organized_path or media.original_path
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no disco")

    mime_type, _ = mimetypes.guess_type(filepath)
    return FileResponse(filepath, media_type=mime_type or "application/octet-stream")


@router.get("/{media_id}/thumbnail")
def get_thumbnail(media_id: int, size: int = Query(300, ge=50, le=800), db: Session = Depends(get_db)):
    """Retorna thumbnail da mídia com cache persistente."""
    media = db.query(Media).get(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Mídia não encontrada")

    filepath = media.organized_path or media.original_path
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no disco")

    # Diretório de cache de thumbnails
    cache_dir = os.path.join(settings.organized_dir, ".thumbnails", "images")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{media_id}_{size}.jpg")

    # Verifica se cache ainda é válido (mesmo mtime do arquivo)
    cache_valid = False
    if os.path.exists(cache_path):
        try:
            source_mtime = os.path.getmtime(filepath)
            cache_mtime = os.path.getmtime(cache_path)
            # Cache válido se foi modificado depois do arquivo original
            cache_valid = cache_mtime >= source_mtime
        except Exception:
            cache_valid = False

    # Se cache não está válido, regenera
    if not cache_valid:
        try:
            if media.media_type == "image":
                from PIL import Image

                img = Image.open(filepath)
                img.thumbnail((size, size))

                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(cache_path, format="JPEG", quality=80)
            else:
                # Para vídeos, gera thumbnail
                from app.services.organizer import generate_video_thumbnail
                from PIL import Image

                # Gera thumbnail temporário de vídeo
                thumb_tmp = cache_path + ".tmp"
                generate_video_thumbnail(filepath, thumb_tmp)

                if os.path.exists(thumb_tmp):
                    img = Image.open(thumb_tmp)
                    img.thumbnail((size, size))
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    img.save(cache_path, format="JPEG", quality=80)
                    os.unlink(thumb_tmp)
                else:
                    raise HTTPException(status_code=404, detail="Thumbnail não disponível para este vídeo")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erro ao gerar thumbnail para {media_id}: {e}")
            raise HTTPException(status_code=500, detail="Erro ao gerar thumbnail")

    # Retorna arquivo do cache com headers de cache HTTP
    if os.path.exists(cache_path):
        return FileResponse(
            cache_path,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=31536000",  # 1 ano
                "ETag": f'"{media_id}_{size}_{int(os.path.getmtime(cache_path))}"'
            }
        )

    raise HTTPException(status_code=404, detail="Thumbnail não disponível")


@router.get("/{media_id}/transcode-status")
def transcode_status(media_id: int, db: Session = Depends(get_db)):
    """Retorna progresso da transcodificação de um vídeo."""
    media = db.query(Media).get(media_id)
    if not media or media.media_type != "video":
        raise HTTPException(status_code=404, detail="Vídeo não encontrado")

    filepath = media.organized_path or media.original_path
    if not filepath:
        return {"status": "idle", "progress": 0}

    from app.services.transcoder import get_transcode_progress
    return get_transcode_progress(filepath)


@router.post("/{media_id}/transcode")
def force_transcode(media_id: int, db: Session = Depends(get_db)):
    """Força transcodificação de um vídeo que não toca no browser."""
    media = db.query(Media).get(media_id)
    if not media or media.media_type != "video":
        raise HTTPException(status_code=404, detail="Vídeo não encontrado")

    filepath = media.organized_path or media.original_path
    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no disco")

    # Bloqueia transcodificação em library_folders se não autorizado
    if _is_in_library_folder(filepath) and not settings.allow_library_modify:
        raise HTTPException(status_code=403, detail="Modificação de arquivos em pastas de biblioteca não autorizada. Ative 'Permitir modificar biblioteca' nas configurações.")

    from app.services.transcoder import get_transcoded_path, is_transcoded, transcode_video
    import threading

    if is_transcoded(filepath):
        return {"status": "already_transcoded", "message": "Já existe versão convertida."}

    # Marca no banco
    media.needs_transcode = True
    db.commit()

    # Inicia transcodificação em background
    transcoded_path = get_transcoded_path(filepath)
    lock_file = transcoded_path + ".lock"
    if not os.path.exists(lock_file):
        with open(lock_file, "w") as f:
            f.write("transcoding")

        def _transcode():
            try:
                transcode_video(filepath)
            finally:
                if os.path.exists(lock_file):
                    os.remove(lock_file)

        threading.Thread(target=_transcode, daemon=True).start()

    return {"status": "transcoding", "message": "Conversão iniciada. Tente novamente em instantes."}


@router.delete("/{media_id}/original")
def delete_original_video(media_id: int, db: Session = Depends(get_db)):
    """Move o vídeo original para FOTOS/trash após transcodificação."""
    media = db.query(Media).get(media_id)
    if not media or media.media_type != "video":
        raise HTTPException(status_code=404, detail="Vídeo não encontrado")

    filepath = media.organized_path or media.original_path
    if not filepath:
        raise HTTPException(status_code=404, detail="Caminho não encontrado")

    # Bloqueia em library_folders se não autorizado
    if _is_in_library_folder(filepath) and not settings.allow_library_modify:
        raise HTTPException(status_code=403, detail="Modificação de arquivos em pastas de biblioteca não autorizada. Ative 'Permitir modificar biblioteca' nas configurações.")

    from app.services.transcoder import get_transcoded_path, is_transcoded
    import shutil

    if not is_transcoded(filepath):
        raise HTTPException(status_code=400, detail="Vídeo ainda não foi transcodificado")

    transcoded_path = get_transcoded_path(filepath)
    if not os.path.exists(transcoded_path):
        raise HTTPException(status_code=400, detail="Arquivo transcoded não encontrado no disco")

    original_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
    transcoded_size = os.path.getsize(transcoded_path)

    # Mover original para .trash local
    from app.services.organizer import move_to_trash as _move_to_trash
    trash_path = None
    if os.path.exists(filepath):
        trash_path = _move_to_trash(filepath)

    # Atualizar banco para apontar para o transcoded
    try:
        if media.organized_path:
            media.organized_path = transcoded_path
        else:
            media.original_path = transcoded_path
        media.filename = Path(transcoded_path).name
        media.needs_transcode = False
        media.video_codec = "h264"
        db.commit()
    except Exception as e:
        logger.error(f"Erro ao atualizar DB após delete original: {e}")
        db.rollback()

    saved_mb = (original_size - transcoded_size) / 1024 / 1024
    return {
        "status": "moved_to_trash",
        "trash_path": trash_path,
        "saved_bytes": original_size - transcoded_size,
        "message": f"Original movido para trash. Economizou {saved_mb:.1f} MB.",
    }


@router.get("/{media_id}/stream")
def stream_video(media_id: int, request: Request, db: Session = Depends(get_db)):
    """Streaming de vídeo com suporte a Range requests."""
    media = db.query(Media).get(media_id)
    if not media or media.media_type != "video":
        raise HTTPException(status_code=404, detail="Vídeo não encontrado")

    filepath = media.organized_path or media.original_path
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no disco")

    from app.services.transcoder import get_playable_path, is_transcoded, get_transcoded_path, needs_transcode_check
    import threading

    if needs_transcode_check(media) and not is_transcoded(filepath):
        # Iniciar transcodificação em background se não estiver rodando
        transcoded_path = get_transcoded_path(filepath)
        lock_file = transcoded_path + ".lock"
        if not os.path.exists(lock_file):
            with open(lock_file, "w") as f:
                f.write("transcoding")

            def _transcode():
                try:
                    get_playable_path(media)
                finally:
                    if os.path.exists(lock_file):
                        os.remove(lock_file)

            threading.Thread(target=_transcode, daemon=True).start()

        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=202,
            content={"status": "transcoding", "message": "Vídeo sendo convertido, tente novamente em instantes."}
        )

    try:
        playable = get_playable_path(media)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"Erro na transcodificação: {e}")

    file_size = os.path.getsize(playable)
    mime_type = "video/mp4" if playable.endswith(".mp4") else (mimetypes.guess_type(playable)[0] or "video/mp4")

    # Suporte a Range requests para seek e playback correto
    range_header = request.headers.get("range")
    if range_header:
        # Parsear Range: bytes=start-end
        range_spec = range_header.replace("bytes=", "")
        parts = range_spec.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
        end = min(end, file_size - 1)
        content_length = end - start + 1

        def iter_file():
            with open(playable, "rb") as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk_size = min(1024 * 1024, remaining)
                    data = f.read(chunk_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            iter_file(),
            status_code=206,
            media_type=mime_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
            },
        )

    # Sem Range: retorna o arquivo completo com Accept-Ranges
    def iter_full():
        with open(playable, "rb") as f:
            while chunk := f.read(1024 * 1024):
                yield chunk

    return StreamingResponse(
        iter_full(),
        media_type=mime_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        },
    )


def _media_to_dict(media: Media, include_details: bool = False) -> dict:
    """Converte objeto Media para dicionário."""
    result = {
        "id": media.id,
        "filename": media.filename,
        "media_type": media.media_type,
        "date_taken": media.date_taken.isoformat() if media.date_taken else None,
        "width": media.width,
        "height": media.height,
        "ai_description": media.ai_description,
        "ai_location": media.ai_location,
        "ai_scene_type": media.ai_scene_type,
        "thumbnail_url": f"/api/media/{media.id}/thumbnail",
        "file_url": f"/api/media/{media.id}/file",
    }

    if media.media_type == "video":
        from app.services.transcoder import is_transcoded, needs_transcode_check, get_transcoded_path
        from pathlib import Path as _Path
        filepath = media.organized_path or media.original_path
        result["stream_url"] = f"/api/media/{media.id}/stream"
        result["duration_seconds"] = media.duration_seconds
        result["needs_transcode"] = needs_transcode_check(media)
        if result["needs_transcode"]:
            transcoded = is_transcoded(filepath)
            result["is_transcoded"] = transcoded
            # Mostrar nome do transcoded quando existe
            if transcoded:
                result["filename"] = _Path(get_transcoded_path(filepath)).name

    if include_details:
        result["organized_path"] = media.organized_path
        result["ai_objects"] = media.ai_objects
        result["latitude"] = media.latitude
        result["longitude"] = media.longitude
        result["camera_make"] = media.camera_make
        result["camera_model"] = media.camera_model
        result["tags"] = [{"id": t.id, "name": t.name, "category": t.category} for t in media.tags]
        result["faces"] = [
            {
                "id": f.id,
                "person_id": f.person_id,
                "person_name": f.person.name if f.person else None,
                "bbox": {"x": f.bbox_x, "y": f.bbox_y, "w": f.bbox_width, "h": f.bbox_height},
                "confidence": f.confidence,
                "is_confirmed": f.is_confirmed,
                "is_ignored": f.is_ignored,
            }
            for f in media.faces
        ]

    return result


@router.delete("/{media_id}")
def delete_media(
    media_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Exclui uma mídia: move o arquivo para trash e remove do banco.
    Para arquivos em library_folders, requer allow_library_modify = true.
    Para arquivos em organized_dir, sempre permitido (move para trash).
    """
    import shutil

    media = db.query(Media).get(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Mídia não encontrada")

    filepath = media.organized_path or media.original_path
    if not filepath:
        raise HTTPException(status_code=404, detail="Caminho não encontrado")

    # Verifica permissão para library_folders
    if _is_in_library_folder(filepath) and not settings.allow_library_modify:
        raise HTTPException(
            status_code=403,
            detail="Modificação de arquivos em pastas de biblioteca não autorizada. Ative 'Permitir modificar biblioteca' nas configurações."
        )

    # Move para .trash (nunca deleta)
    # Cada pasta tem seu próprio .trash local
    if _is_in_library_folder(filepath):
        # Encontra qual library_folder contém o arquivo
        abs_path = os.path.abspath(filepath)
        trash_dir = None
        for folder in settings.library_folders:
            abs_folder = os.path.abspath(folder)
            if abs_path.startswith(abs_folder + os.sep):
                trash_dir = os.path.join(folder, ".trash")
                break
        if not trash_dir:
            trash_dir = os.path.join(settings.organized_dir, ".trash")
    else:
        trash_dir = os.path.join(settings.organized_dir, ".trash")

    os.makedirs(trash_dir, exist_ok=True)
    trash_path = os.path.join(trash_dir, Path(filepath).name)

    # Evitar conflito de nomes
    if os.path.exists(trash_path):
        stem = Path(filepath).stem
        ext = Path(filepath).suffix
        i = 1
        while os.path.exists(trash_path):
            trash_path = os.path.join(trash_dir, f"{stem}_{i}{ext}")
            i += 1

    if os.path.exists(filepath):
        shutil.move(filepath, trash_path)

    # Remove faces associadas
    for face in media.faces:
        db.delete(face)

    # Remove do banco
    db.delete(media)
    db.commit()

    return {"status": "ok", "message": f"Arquivo movido para trash: {Path(trash_path).name}"}
