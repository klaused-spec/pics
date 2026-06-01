"""
Endpoints de mídia: listagem, busca, detalhes, thumbnail, streaming.
"""
import os
import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.config import settings
from app.models import Media, Tag, Person, Face
from app.services.ai_vision import search_by_description

router = APIRouter(prefix="/media", tags=["media"])


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
    media_type: Optional[str] = None,
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


@router.delete("/duplicates/all")
def delete_all_duplicates(db: Session = Depends(get_db)):
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

    from app.services.transcoder import get_transcoded_path, is_transcoded
    import shutil

    if not is_transcoded(filepath):
        raise HTTPException(status_code=400, detail="Vídeo ainda não foi transcodificado")

    transcoded_path = get_transcoded_path(filepath)
    original_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
    transcoded_size = os.path.getsize(transcoded_path)

    # Mover original para .trash local
    from app.services.organizer import move_to_trash as _move_to_trash
    trash_path = None
    if os.path.exists(filepath):
        trash_path = _move_to_trash(filepath)

    # Atualizar banco para apontar para o transcoded
    if media.organized_path:
        media.organized_path = transcoded_path
    else:
        media.original_path = transcoded_path
    media.filename = Path(transcoded_path).name
    media.needs_transcode = False
    media.video_codec = "h264"
    db.commit()

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
def delete_media(media_id: int, db: Session = Depends(get_db)):
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
