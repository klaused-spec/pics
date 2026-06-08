"""
Endpoints de pessoas e rostos.
"""
import os
import pickle
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
import cv2
import numpy as np

from app.core.database import get_db
from app.models import Person, Face, Media
from app.services.face_recognition_service import (
    assign_face_to_person, create_person, merge_persons, cluster_unknown_faces,
    create_manual_face,
)

router = APIRouter(prefix="/persons", tags=["persons"])


class PersonCreate(BaseModel):
    name: str


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    avatar_face_id: Optional[int] = None


class FaceAssign(BaseModel):
    person_id: int


class MergePersons(BaseModel):
    keep_id: int
    merge_id: int


class ManualFaceCreate(BaseModel):
    media_id: int
    bbox_x: int
    bbox_y: int
    bbox_width: int
    bbox_height: int


@router.get("/")
def list_persons(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Lista todas as pessoas cadastradas."""
    query = db.query(Person)
    total = query.count()
    items = query.order_by(Person.name).offset((page - 1) * per_page).limit(per_page).all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "is_confirmed": p.is_confirmed,
                "face_count": len(p.faces),
                "media_count": db.query(Media).join(Media.faces).filter(Face.person_id == p.id).distinct().count(),
                "avatar_face_id": p.avatar_face_id or (p.faces[0].id if p.faces else None),
            }
            for p in items
        ],
    }


@router.post("/")
def create_new_person(data: PersonCreate, db: Session = Depends(get_db)):
    """Cria uma nova pessoa."""
    person = create_person(data.name, db)
    return {"id": person.id, "name": person.name, "is_confirmed": person.is_confirmed}


@router.put("/{person_id}")
def update_person(person_id: int, data: PersonUpdate, db: Session = Depends(get_db)):
    """Atualiza dados de uma pessoa."""
    person = db.query(Person).get(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")

    if data.name is not None:
        person.name = data.name
        person.is_confirmed = True
    if data.avatar_face_id is not None:
        person.avatar_face_id = data.avatar_face_id
    db.commit()

    return {"id": person.id, "name": person.name, "is_confirmed": person.is_confirmed}


@router.delete("/{person_id}")
def delete_person(person_id: int, db: Session = Depends(get_db)):
    """Remove uma pessoa (rostos ficam sem associação)."""
    person = db.query(Person).get(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")

    try:
        # Desassocia rostos
        faces_to_update = list(person.faces)
        for face in faces_to_update:
            face.person_id = None
            face.is_confirmed = False
        
        # Delete person
        db.delete(person)
        db.commit()
        
        return {
            "message": "Pessoa removida com sucesso",
            "faces_unlinked": len(faces_to_update)
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao deletar pessoa: {str(e)}")


@router.get("/{person_id}/media")
def get_person_media(
    person_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Lista mídias onde a pessoa aparece."""
    person = db.query(Person).get(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")

    query = db.query(Media).join(Media.faces).filter(
        Face.person_id == person_id,
        Media.is_duplicate == False,
    ).distinct()

    total = query.count()
    items = query.order_by(Media.date_taken.desc()).offset((page - 1) * per_page).limit(per_page).all()

    from app.api.media import _media_to_dict
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "person": {
            "id": person.id,
            "name": person.name,
            "avatar_face_id": person.avatar_face_id or (person.faces[0].id if person.faces else None),
            "face_ids": [f.id for f in person.faces if not f.is_ignored],
        },
        "items": [_media_to_dict(m) for m in items],
    }


@router.post("/faces/{face_id}/assign")
def assign_face(face_id: int, data: FaceAssign, db: Session = Depends(get_db)):
    """Atribui um rosto a uma pessoa (marcação manual)."""
    face = db.query(Face).get(face_id)
    if not face:
        raise HTTPException(status_code=404, detail="Rosto não encontrado")

    person = db.query(Person).get(data.person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")

    assign_face_to_person(face_id, data.person_id, db)
    return {"message": "Rosto atribuído com sucesso"}


@router.post("/faces/{face_id}/unassign")
def unassign_face(face_id: int, db: Session = Depends(get_db)):
    """Remove a associação de um rosto com uma pessoa."""
    face = db.query(Face).get(face_id)
    if not face:
        raise HTTPException(status_code=404, detail="Rosto não encontrado")

    face.person_id = None
    face.is_confirmed = False
    face.confidence = None
    db.commit()
    return {"message": "Associação removida"}


@router.post("/faces/{face_id}/confirm")
def confirm_face(face_id: int, db: Session = Depends(get_db)):
    """Aprova a sugestão de identificação de um rosto."""
    face = db.query(Face).get(face_id)
    if not face:
        raise HTTPException(status_code=404, detail="Rosto não encontrado")
    if not face.person_id:
        raise HTTPException(status_code=400, detail="Rosto não tem pessoa sugerida")

    face.is_confirmed = True
    face.confidence = 1.0
    db.commit()
    return {"message": "Identificação confirmada"}


@router.post("/faces/{face_id}/ignore")
def ignore_face(face_id: int, db: Session = Depends(get_db)):
    """Marca um rosto como ignorado (não aparece mais na UI)."""
    face = db.query(Face).get(face_id)
    if not face:
        raise HTTPException(status_code=404, detail="Rosto não encontrado")

    face.is_ignored = True
    face.person_id = None
    face.is_confirmed = False
    db.commit()
    return {"message": "Rosto ignorado"}


@router.post("/merge")
def merge(data: MergePersons, db: Session = Depends(get_db)):
    """Mescla duas pessoas em uma."""
    keep = db.query(Person).get(data.keep_id)
    merge_target = db.query(Person).get(data.merge_id)
    if not keep or not merge_target:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")

    merge_persons(data.keep_id, data.merge_id, db)
    return {"message": f"Pessoa mesclada em {keep.name}"}


@router.post("/cluster")
def run_clustering(db: Session = Depends(get_db)):
    """Agrupa rostos desconhecidos sem criar pessoas. Retorna clusters de face IDs."""
    result = cluster_unknown_faces(db)
    return result


@router.post("/faces/manual")
def create_manual_face_endpoint(data: ManualFaceCreate, db: Session = Depends(get_db)):
    """Cria um rosto manualmente a partir de seleção do usuário na imagem."""
    media = db.query(Media).get(data.media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Mídia não encontrada")

    face = create_manual_face(
        media=media,
        bbox_x=data.bbox_x,
        bbox_y=data.bbox_y,
        bbox_width=data.bbox_width,
        bbox_height=data.bbox_height,
        db=db,
    )
    if not face:
        raise HTTPException(status_code=400, detail="Não foi possível extrair embedding da região selecionada")

    return {
        "id": face.id,
        "bbox": {"x": face.bbox_x, "y": face.bbox_y, "w": face.bbox_width, "h": face.bbox_height},
        "person_name": None,
        "is_confirmed": False,
    }


@router.get("/faces/pending")
def list_pending_faces(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Lista rostos não identificados e não ignorados, com sugestões."""
    query = db.query(Face).filter(
        Face.is_ignored == False,
    ).order_by(Face.id.desc())

    # Inclui tanto faces sem pessoa quanto com sugestão pendente
    from sqlalchemy import or_
    query = query.filter(
        or_(
            Face.person_id.is_(None),
            Face.is_confirmed == False,
        )
    )

    total = query.count()
    faces = query.offset((page - 1) * per_page).limit(per_page).all()

    items = []
    for f in faces:
        # Pega a primeira media associada para contexto
        media = f.media_items[0] if f.media_items else None
        items.append({
            "id": f.id,
            "bbox": {"x": f.bbox_x, "y": f.bbox_y, "w": f.bbox_width, "h": f.bbox_height},
            "person_id": f.person_id,
            "person_name": f.person.name if f.person else None,
            "confidence": f.confidence,
            "is_confirmed": f.is_confirmed,
            "media_id": media.id if media else None,
            "media_filename": media.filename if media else None,
        })

    return {"total": total, "page": page, "per_page": per_page, "items": items}


@router.get("/faces/all")
def list_all_faces(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    person_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Lista TODOS os rostos (incluindo confirmados e ignorados)."""
    query = db.query(Face).order_by(Face.id.desc())

    if person_id is not None:
        query = query.filter(Face.person_id == person_id)

    total = query.count()
    faces = query.offset((page - 1) * per_page).limit(per_page).all()

    items = []
    for f in faces:
        media = f.media_items[0] if f.media_items else None
        items.append({
            "id": f.id,
            "bbox": {"x": f.bbox_x, "y": f.bbox_y, "w": f.bbox_width, "h": f.bbox_height},
            "person_id": f.person_id,
            "person_name": f.person.name if f.person else None,
            "confidence": f.confidence,
            "is_confirmed": f.is_confirmed,
            "is_ignored": f.is_ignored,
            "media_id": media.id if media else None,
            "media_filename": media.filename if media else None,
        })

    return {"total": total, "page": page, "per_page": per_page, "items": items}


@router.delete("/faces/{face_id}")
def delete_face(face_id: int, db: Session = Depends(get_db)):
    """Remove um rosto do banco de dados."""
    face = db.query(Face).get(face_id)
    if not face:
        raise HTTPException(status_code=404, detail="Rosto não encontrado")
    db.delete(face)
    db.commit()
    return {"message": "Rosto removido"}


@router.get("/faces/{face_id}/thumbnail")
def get_face_thumbnail(face_id: int, size: int = Query(120, ge=40, le=400), db: Session = Depends(get_db)):
    """Retorna thumbnail do rosto cortado da imagem original."""
    face = db.query(Face).get(face_id)
    if not face:
        raise HTTPException(status_code=404, detail="Rosto não encontrado")

    media = face.media_items[0] if face.media_items else None
    if not media:
        raise HTTPException(status_code=404, detail="Mídia não encontrada para este rosto")

    filepath = media.organized_path or media.original_path
    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    img = cv2.imread(filepath)
    if img is None:
        raise HTTPException(status_code=500, detail="Não foi possível ler a imagem")

    img_h, img_w = img.shape[:2]

    # Crop com margem
    margin = int(max(face.bbox_width or 0, face.bbox_height or 0) * 0.2)
    x = max(0, (face.bbox_x or 0) - margin)
    y = max(0, (face.bbox_y or 0) - margin)
    x2 = min(img_w, (face.bbox_x or 0) + (face.bbox_width or 0) + margin)
    y2 = min(img_h, (face.bbox_y or 0) + (face.bbox_height or 0) + margin)

    crop = img[y:y2, x:x2]
    if crop.size == 0:
        raise HTTPException(status_code=500, detail="Crop vazio")

    # Resize mantendo proporção
    h, w = crop.shape[:2]
    scale = size / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(crop, (new_w, new_h))

    _, buf = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return Response(content=buf.tobytes(), media_type="image/jpeg")
