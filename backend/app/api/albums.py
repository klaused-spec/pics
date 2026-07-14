"""
Endpoints de álbuns: CRUD e gerenciamento de mídias.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Album, Media, album_media

router = APIRouter(prefix="/albums", tags=["albums"])


class AlbumCreate(BaseModel):
    name: str
    description: Optional[str] = None
    media_ids: Optional[list[int]] = None


class AlbumUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    cover_media_id: Optional[int] = None


class AlbumAddMedia(BaseModel):
    media_ids: list[int]


@router.get("/")
def list_albums(
    include_items: bool = Query(False),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista todos os álbuns com contagem de mídias."""
    albums = db.query(Album).order_by(Album.updated_at.desc()).all()
    return [_album_to_dict(a, db, include_items=include_items) for a in albums]


@router.post("/", status_code=201)
def create_album(
    current_user: dict = Depends(get_current_user),
    data: AlbumCreate = None,
    db: Session = Depends(get_db),
):
    """Cria um novo álbum, opcionalmente já com mídias."""
    album = Album(name=data.name, description=data.description)
    db.add(album)
    db.flush()

    if data.media_ids:
        existing_ids = set()
        for media_id in data.media_ids:
            if media_id in existing_ids:
                continue
            media = db.query(Media).filter(Media.id == media_id).first()
            if media:
                album.media_items.append(media)
                existing_ids.add(media_id)
        if not album.cover_media_id and album.media_items:
            album.cover_media_id = album.media_items[0].id

    db.commit()
    db.refresh(album)
    return _album_to_dict(album, db, include_items=True)


@router.get("/{album_id}")
def get_album(album_id: int, db: Session = Depends(get_db)):
    """Retorna detalhes de um álbum."""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Álbum não encontrado")
    return _album_to_dict(album, db)


@router.put("/{album_id}")
def update_album(album_id: int, data: AlbumUpdate, db: Session = Depends(get_db)):
    """Atualiza nome, descrição ou capa de um álbum."""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Álbum não encontrado")

    if data.name is not None:
        album.name = data.name
    if data.description is not None:
        album.description = data.description
    if data.cover_media_id is not None:
        album.cover_media_id = data.cover_media_id

    db.commit()
    db.refresh(album)
    return _album_to_dict(album, db)


@router.delete("/{album_id}", status_code=204)
def delete_album(album_id: int, db: Session = Depends(get_db)):
    """Remove um álbum (não apaga as mídias)."""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Álbum não encontrado")
    db.delete(album)
    db.commit()


@router.get("/{album_id}/media")
def get_album_media(
    album_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(60, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Lista mídias de um álbum com paginação."""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Álbum não encontrado")

    query = db.query(Media).join(album_media).filter(album_media.c.album_id == album_id)
    total = query.count()
    items = (
        query.order_by(Media.date_taken.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "album": _album_to_dict(album, db),
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "items": [_media_to_dict(m) for m in items],
    }


@router.post("/{album_id}/media")
def add_media_to_album(album_id: int, data: AlbumAddMedia, db: Session = Depends(get_db)):
    """Adiciona mídias a um álbum."""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Álbum não encontrado")

    existing_ids = {m.id for m in album.media_items}
    added = 0
    for media_id in data.media_ids:
        if media_id not in existing_ids:
            media = db.query(Media).filter(Media.id == media_id).first()
            if media:
                album.media_items.append(media)
                added += 1

    # Define capa automaticamente se não tiver
    if not album.cover_media_id and album.media_items:
        album.cover_media_id = album.media_items[0].id

    db.commit()
    return {"added": added, "total": len(album.media_items)}


@router.delete("/{album_id}/media")
def remove_media_from_album(album_id: int, data: AlbumAddMedia, db: Session = Depends(get_db)):
    """Remove mídias de um álbum."""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Álbum não encontrado")

    removed = 0
    for media_id in data.media_ids:
        media = db.query(Media).filter(Media.id == media_id).first()
        if media and media in album.media_items:
            album.media_items.remove(media)
            removed += 1

    db.commit()
    return {"removed": removed, "total": len(album.media_items)}


def _album_to_dict(album: Album, db: Session, include_items: bool = False) -> dict:
    """Converte álbum para dicionário."""
    count = db.query(func.count(album_media.c.media_id)).filter(
        album_media.c.album_id == album.id
    ).scalar()

    result = {
        "id": album.id,
        "name": album.name,
        "description": album.description,
        "cover_media_id": album.cover_media_id,
        "media_count": count,
        "created_at": album.created_at.isoformat() if album.created_at else None,
        "updated_at": album.updated_at.isoformat() if album.updated_at else None,
    }

    if include_items:
        item_ids = [
            row[0]
            for row in db.query(album_media.c.media_id)
            .filter(album_media.c.album_id == album.id)
            .all()
        ]
        result["item_ids"] = item_ids

    return result


def _media_to_dict(media: Media) -> dict:
    """Converte mídia para dicionário simplificado."""
    return {
        "id": media.id,
        "filename": media.filename,
        "media_type": media.media_type,
        "date_taken": media.date_taken.isoformat() if media.date_taken else None,
        "width": media.width,
        "height": media.height,
        "ai_description": media.ai_description,
    }
