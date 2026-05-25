"""
Endpoints de mídia: listagem, busca, detalhes, thumbnail, streaming.
"""
import os
import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.config import settings
from app.models import Media, Tag, Person, Face
from app.services.ai_vision import search_by_description

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/")
def list_media(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    media_type: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    day: Optional[int] = None,
    person_id: Optional[int] = None,
    tag: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Lista mídias com paginação e filtros."""
    query = db.query(Media).filter(Media.is_duplicate == False, Media.is_organized == True)

    if media_type:
        query = query.filter(Media.media_type == media_type)

    if year:
        query = query.filter(func.extract("year", Media.date_taken) == year)
    if month:
        query = query.filter(func.extract("month", Media.date_taken) == month)
    if day:
        query = query.filter(func.extract("day", Media.date_taken) == day)

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
    db: Session = Depends(get_db),
):
    """Retorna timeline agrupada por ano/mês."""
    results = (
        db.query(
            func.extract("year", Media.date_taken).label("year"),
            func.extract("month", Media.date_taken).label("month"),
            func.count(Media.id).label("count"),
        )
        .filter(Media.is_duplicate == False, Media.is_organized == True)
        .group_by("year", "month")
        .order_by(func.extract("year", Media.date_taken).desc(), func.extract("month", Media.date_taken).desc())
        .all()
    )

    return [
        {"year": int(r.year), "month": int(r.month), "count": r.count}
        for r in results
        if r.year is not None
    ]


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Retorna estatísticas gerais do acervo."""
    total = db.query(Media).filter(Media.is_duplicate == False).count()
    images = db.query(Media).filter(Media.media_type == "image", Media.is_duplicate == False).count()
    videos = db.query(Media).filter(Media.media_type == "video", Media.is_duplicate == False).count()
    duplicates = db.query(Media).filter(Media.is_duplicate == True).count()
    ai_processed = db.query(Media).filter(Media.ai_processed == True).count()
    persons = db.query(Person).count()
    faces = db.query(Face).count()

    return {
        "total_media": total,
        "images": images,
        "videos": videos,
        "duplicates_found": duplicates,
        "ai_processed": ai_processed,
        "persons": persons,
        "faces_detected": faces,
    }


@router.get("/{media_id}")
def get_media(media_id: int, db: Session = Depends(get_db)):
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
    """Retorna thumbnail da mídia."""
    media = db.query(Media).get(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Mídia não encontrada")

    filepath = media.organized_path or media.original_path
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no disco")

    if media.media_type == "image":
        from PIL import Image
        import io

        img = Image.open(filepath)
        img.thumbnail((size, size))

        # Converte para JPEG
        buffer = io.BytesIO()
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(buffer, format="JPEG", quality=80)
        buffer.seek(0)

        return StreamingResponse(buffer, media_type="image/jpeg")
    else:
        # Para vídeos, tenta usar thumbnail pré-gerado
        from app.services.organizer import generate_video_thumbnail
        thumb_dir = os.path.join(settings.organized_dir, ".thumbnails", "videos")
        thumb_path = os.path.join(thumb_dir, f"{Path(media.filename).stem}.jpg")

        # Se não existe, gera agora
        if not os.path.exists(thumb_path):
            generate_video_thumbnail(filepath, thumb_path)

        if os.path.exists(thumb_path):
            from PIL import Image
            import io
            img = Image.open(thumb_path)
            img.thumbnail((size, size))
            buffer = io.BytesIO()
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(buffer, format="JPEG", quality=80)
            buffer.seek(0)
            return StreamingResponse(buffer, media_type="image/jpeg")

        raise HTTPException(status_code=404, detail="Thumbnail não disponível para este vídeo")


@router.get("/{media_id}/stream")
def stream_video(media_id: int, db: Session = Depends(get_db)):
    """Streaming de vídeo. Transcodifica sob demanda se codec incompatível."""
    media = db.query(Media).get(media_id)
    if not media or media.media_type != "video":
        raise HTTPException(status_code=404, detail="Vídeo não encontrado")

    filepath = media.organized_path or media.original_path
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no disco")

    from app.services.transcoder import get_playable_path
    try:
        playable = get_playable_path(media)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"Erro na transcodificação: {e}")

    mime_type = "video/mp4" if playable.endswith(".mp4") else (mimetypes.guess_type(playable)[0] or "video/mp4")
    return FileResponse(playable, media_type=mime_type)


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
        result["stream_url"] = f"/api/media/{media.id}/stream"
        result["duration_seconds"] = media.duration_seconds

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
