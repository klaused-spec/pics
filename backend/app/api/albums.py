"""
Endpoints de álbuns: CRUD e gerenciamento de mídias.
"""
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Album, Media, AlbumTranscodeJob, album_media

router = APIRouter(prefix="/albums", tags=["albums"])


class AlbumCreate(BaseModel):
    name: str
    description: Optional[str] = None
    media_ids: Optional[list[int]] = None


class AlbumUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    cover_media_id: Optional[int] = None
    transcoded_only: Optional[bool] = None


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
    if data.transcoded_only is not None:
        album.transcoded_only = data.transcoded_only

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
    new_ids = []
    added = 0
    for media_id in data.media_ids:
        if media_id not in existing_ids:
            media = db.query(Media).filter(Media.id == media_id).first()
            if media:
                album.media_items.append(media)
                new_ids.append(media_id)
                added += 1

    if not album.cover_media_id and album.media_items:
        album.cover_media_id = album.media_items[0].id

    db.commit()

    return {"added": added, "total": len(album.media_items)}


@router.delete("/{album_id}/media")
def remove_media_from_album(album_id: int, data: AlbumAddMedia, db: Session = Depends(get_db)):
    """Remove mídias de um álbum e apaga arquivos otimizados."""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Álbum não encontrado")

    removed = 0
    for media_id in data.media_ids:
        media = db.query(Media).filter(Media.id == media_id).first()
        if media and media in album.media_items:
            album.media_items.remove(media)
            removed += 1
            # Remove job e arquivo otimizado
            job = db.query(AlbumTranscodeJob).filter_by(album_id=album_id, media_id=media_id).first()
            if job:
                if job.output_path and os.path.isfile(job.output_path):
                    try:
                        os.remove(job.output_path)
                    except OSError:
                        pass
                db.delete(job)

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
        "transcoded_only": bool(album.transcoded_only),
        "media_count": count,
        "created_at": album.created_at.isoformat() if album.created_at else None,
        "updated_at": album.updated_at.isoformat() if album.updated_at else None,
    }

    if include_items:
        item_ids = [
            row[0]
            for row in db.query(album_media.c.media_id)
            .filter(album_media.c.album_id == album.id)
            .order_by(album_media.c.position.asc().nullslast(), album_media.c.media_id.asc())
            .all()
        ]
        result["item_ids"] = item_ids

    return result


class AlbumOrder(BaseModel):
    media_ids: list[int]  # IDs na nova ordem desejada


@router.put("/{album_id}/order")
def reorder_album(
    album_id: int,
    data: AlbumOrder,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Define a ordem dos itens do álbum. `media_ids` é a lista completa na nova ordem."""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Álbum não encontrado")
    for position, media_id in enumerate(data.media_ids):
        db.execute(
            album_media.update()
            .where(album_media.c.album_id == album_id)
            .where(album_media.c.media_id == media_id)
            .values(position=position)
        )
    db.commit()
    return {"ok": True}


@router.post("/{album_id}/transcode")
def start_transcode(
    album_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Inicia (ou retoma) otimização de todas as mídias do álbum (fotos + vídeos)."""
    from app.services.transcode_service import ensure_transcode_jobs, start_album_transcode

    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Álbum não encontrado")

    # Todas as mídias do álbum (fotos e vídeos)
    all_ids = [
        row[0]
        for row in db.query(Media.id)
        .join(album_media, Media.id == album_media.c.media_id)
        .filter(album_media.c.album_id == album_id)
        .all()
    ]
    if not all_ids:
        return {"message": "Álbum vazio", "jobs": []}

    jobs = ensure_transcode_jobs(db, album_id, all_ids)

    # Dispara apenas os que ainda não estão done ("running" pode ser órfão de restart)
    pending_ids = [j.id for j in jobs if j.status in ("pending", "failed", "running")]
    if pending_ids:
        start_album_transcode(album_id, pending_ids)

    return {
        "message": f"{len(pending_ids)} mídia(s) enfileirada(s)",
        "total": len(jobs),
        "pending": len(pending_ids),
    }


@router.get("/{album_id}/transcode/status")
def transcode_status(
    album_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retorna progresso da transcodificação do álbum."""
    from app.services.transcode_service import get_album_transcode_status
    return get_album_transcode_status(db, album_id)


@router.post("/{album_id}/transcode/reset")
def transcode_reset(
    album_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reseta todos os jobs do álbum para pending, apaga arquivos gerados e reprocessa."""
    import shutil
    from app.services.transcode_service import start_album_transcode

    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Álbum não encontrado")

    jobs = db.query(AlbumTranscodeJob).filter_by(album_id=album_id).all()
    for job in jobs:
        # Apaga arquivo otimizado do disco
        if job.output_path and os.path.exists(job.output_path):
            try:
                os.remove(job.output_path)
            except Exception:
                pass
        job.status = "pending"
        job.error_message = None
        job.output_path = None

    # Recalcula output_path correto para cada job
    from app.services.transcode_service import output_path_for
    for job in jobs:
        media = db.query(Media).filter_by(id=job.media_id).first()
        if media:
            job.output_path = output_path_for(album_id, job.media_id, media.media_type, album.name, media.filename)
            media.transcoded_path = None

    db.commit()

    pending_ids = [j.id for j in jobs]
    if pending_ids:
        start_album_transcode(album_id, pending_ids)

    return {"reset": len(jobs), "reprocessing": len(pending_ids)}


@router.get("/transcode/file/{job_id}")
def serve_optimized_file(
    job_id: int,
    request: Request,
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Serve o arquivo otimizado (foto JPEG ou vídeo MP4) com suporte a HTTP Range."""
    from fastapi.responses import StreamingResponse
    import mimetypes

    # Auth via Bearer ou ?token=
    from app.core.security import verify_token
    auth = request.headers.get("Authorization", "")
    t = token or (auth.replace("Bearer ", "") if auth.startswith("Bearer ") else None)
    if not t:
        raise HTTPException(status_code=401, detail="Não autenticado")
    try:
        verify_token(t)
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")

    job = db.query(AlbumTranscodeJob).filter_by(id=job_id).first()
    if not job or job.status != "done":
        raise HTTPException(status_code=404, detail="Arquivo otimizado não disponível")
    if not job.output_path or not os.path.isfile(job.output_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no disco")

    filepath = job.output_path
    file_size = os.path.getsize(filepath)
    mime_type = "video/mp4" if filepath.endswith(".mp4") else "image/jpeg"

    range_header = request.headers.get("Range")
    if not range_header:
        def _full():
            with open(filepath, "rb") as f:
                while chunk := f.read(1 << 20):
                    yield chunk
        return StreamingResponse(_full(), media_type=mime_type, headers={
            "Accept-Ranges": "bytes", "Content-Length": str(file_size),
        })

    try:
        range_val = range_header.replace("bytes=", "")
        start_str, _, end_str = range_val.partition("-")
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
    except ValueError:
        raise HTTPException(status_code=416, detail="Range inválido")

    if start >= file_size or end >= file_size or start > end:
        raise HTTPException(status_code=416, detail="Range fora dos limites",
                            headers={"Content-Range": f"bytes */{file_size}"})

    chunk_size = end - start + 1

    def _range():
        with open(filepath, "rb") as f:
            f.seek(start)
            remaining = chunk_size
            while remaining > 0:
                data = f.read(min(1 << 20, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    return StreamingResponse(_range(), status_code=206, media_type=mime_type, headers={
        "Accept-Ranges": "bytes",
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(chunk_size),
    })


def _media_to_dict(media: Media) -> dict:
    """Converte mídia para dicionário.

    Inclui os campos que o app mobile usa para renderizar a grade do álbum
    (thumbnail_url, duration_seconds, sha256_hash), para que álbuns com mídias
    que NÃO estão na lista sincronizada (ex.: duplicadas ou não-organizadas)
    também apareçam. O app resolve thumbnail_url relativo com o baseUrl dele.
    """
    return {
        "id": media.id,
        "filename": media.filename,
        "media_type": media.media_type,
        "date_taken": media.date_taken.isoformat() if media.date_taken else None,
        "updated_at": media.updated_at.isoformat() if media.updated_at else None,
        "width": media.width,
        "height": media.height,
        "duration_seconds": media.duration_seconds,
        "sha256_hash": media.sha256_hash,
        "ai_description": media.ai_description,
        "thumbnail_url": f"/api/media/{media.id}/thumbnail?size=300",
    }
