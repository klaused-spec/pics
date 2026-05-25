"""
Serviço de reconhecimento facial.
Usa MediaPipe para detecção de rostos + ArcFace (w600k_r50) via ONNX Runtime para embeddings.
Gera vetores 512-d altamente discriminativos para identificação de pessoas.
"""
import os
import logging
import pickle
from typing import Optional

import cv2
import numpy as np
from PIL import Image
from sqlalchemy.orm import Session
from sklearn.cluster import DBSCAN
import onnxruntime as ort
import mediapipe as mp

from app.models import Media, Face, Person, media_faces

logger = logging.getLogger(__name__)

# Limiar de similaridade cosseno para considerar mesma pessoa
# ArcFace: > 0.4 é match razoável, > 0.5 é match forte
SIMILARITY_THRESHOLD = 0.45

# Caminho do modelo ArcFace
MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models")
REC_MODEL_PATH = os.path.join(MODELS_DIR, "w600k_r50.onnx")

# Singletons
_rec_session = None


def _get_rec_session():
    """Retorna sessão de reconhecimento ArcFace."""
    global _rec_session
    if _rec_session is None:
        _rec_session = ort.InferenceSession(REC_MODEL_PATH, providers=["CPUExecutionProvider"])
        logger.info("Modelo ArcFace carregado")
    return _rec_session


def _get_face_mesh():
    """Retorna face mesh MediaPipe para landmarks (usado após detecção)."""
    return mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=20,
        min_detection_confidence=0.3,
        refine_landmarks=True,
    )


def _get_face_detector():
    """Retorna detector de faces MediaPipe (modelo full range, melhor para rostos distantes)."""
    return mp.solutions.face_detection.FaceDetection(
        model_selection=1,  # 1 = full range (até 5m), 0 = short range (até 2m)
        min_detection_confidence=0.3,
    )


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Calcula similaridade cosseno entre dois vetores."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _align_face(image_bgr: np.ndarray, landmarks_5: np.ndarray) -> np.ndarray:
    """
    Alinha face usando transformação afim baseada em 5 landmarks.
    Retorna imagem 112x112 alinhada para ArcFace.
    """
    # Template de referência para ArcFace (112x112)
    dst = np.array([
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ], dtype=np.float32)

    src = landmarks_5.astype(np.float32)
    tform = cv2.estimateAffinePartial2D(src, dst)[0]
    if tform is None:
        tform = cv2.getAffineTransform(src[:3], dst[:3])

    aligned = cv2.warpAffine(image_bgr, tform, (112, 112), borderValue=0)
    return aligned


def _get_embedding(face_img: np.ndarray) -> np.ndarray:
    """
    Calcula embedding 512-d de uma face alinhada 112x112 via ArcFace.
    """
    session = _get_rec_session()

    img = face_img.astype(np.float32)
    img = (img - 127.5) / 127.5
    img = img.transpose(2, 0, 1)[np.newaxis, ...]

    input_name = session.get_inputs()[0].name
    embedding = session.run(None, {input_name: img})[0][0]

    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm
    return embedding


# Índices dos 5 pontos-chave no MediaPipe Face Mesh (468 landmarks)
# Olho esquerdo, olho direito, nariz, canto esquerdo boca, canto direito boca
MEDIAPIPE_5_LANDMARKS = {
    "left_eye": [33, 160, 158, 133, 153, 144],
    "right_eye": [362, 385, 387, 263, 373, 380],
    "nose": [1],
    "left_mouth": [61],
    "right_mouth": [291],
}


def detect_faces_in_image(filepath: str) -> list[dict]:
    """
    Detecta rostos usando MediaPipe Face Detection (full range) + Face Mesh para landmarks.
    Face Detection captura rostos distantes; Face Mesh fornece landmarks para alinhamento ArcFace.
    Para rostos detectados sem landmarks (muito pequenos), usa crop direto redimensionado.
    """
    try:
        image_bgr = cv2.imread(filepath)
        if image_bgr is None:
            return []

        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        img_h, img_w = image_bgr.shape[:2]

        # Fase 1: Detecta rostos com Face Detection (full range - rostos distantes)
        detected_boxes = []
        with _get_face_detector() as detector:
            det_results = detector.process(image_rgb)
            if det_results.detections:
                for det in det_results.detections:
                    bbox = det.location_data.relative_bounding_box
                    x = max(0, int(bbox.xmin * img_w))
                    y = max(0, int(bbox.ymin * img_h))
                    w = int(bbox.width * img_w)
                    h = int(bbox.height * img_h)
                    # Garante que não sai da imagem
                    x = min(x, img_w - 1)
                    y = min(y, img_h - 1)
                    w = min(w, img_w - x)
                    h = min(h, img_h - y)
                    if w > 10 and h > 10:
                        detected_boxes.append((x, y, w, h))

        # Fase 2: Face Mesh para landmarks precisos
        mesh_faces = []
        with _get_face_mesh() as mesh:
            results = mesh.process(image_rgb)
            if results.multi_face_landmarks:
                for face_landmarks in results.multi_face_landmarks:
                    landmarks = face_landmarks.landmark

                    xs = [lm.x * img_w for lm in landmarks]
                    ys = [lm.y * img_h for lm in landmarks]
                    x_min, x_max = min(xs), max(xs)
                    y_min, y_max = min(ys), max(ys)

                    bbox_x = max(0, int(x_min))
                    bbox_y = max(0, int(y_min))
                    bbox_w = int(x_max - x_min)
                    bbox_h = int(y_max - y_min)

                    def _center(indices):
                        pts = [[landmarks[i].x * img_w, landmarks[i].y * img_h] for i in indices]
                        return np.mean(pts, axis=0)

                    landmarks_5 = np.array([
                        _center(MEDIAPIPE_5_LANDMARKS["left_eye"]),
                        _center(MEDIAPIPE_5_LANDMARKS["right_eye"]),
                        _center(MEDIAPIPE_5_LANDMARKS["nose"]),
                        _center(MEDIAPIPE_5_LANDMARKS["left_mouth"]),
                        _center(MEDIAPIPE_5_LANDMARKS["right_mouth"]),
                    ], dtype=np.float32)

                    aligned = _align_face(image_bgr, landmarks_5)
                    embedding = _get_embedding(aligned)

                    mesh_faces.append({
                        "bbox_x": bbox_x,
                        "bbox_y": bbox_y,
                        "bbox_width": bbox_w,
                        "bbox_height": bbox_h,
                        "encoding": embedding,
                    })

        # Fase 3: Para cada detecção do Face Detection que NÃO corresponde a um Face Mesh,
        # faz crop direto e resize para 112x112 (rostos pequenos/distantes)
        faces = list(mesh_faces)

        for (dx, dy, dw, dh) in detected_boxes:
            # Verifica se já temos esse rosto via Face Mesh (overlap > 50%)
            already_found = False
            for mf in mesh_faces:
                mx, my, mw, mh = mf["bbox_x"], mf["bbox_y"], mf["bbox_width"], mf["bbox_height"]
                # Calcula IoU simplificado (intersecção sobre menor área)
                ix = max(dx, mx)
                iy = max(dy, my)
                ix2 = min(dx + dw, mx + mw)
                iy2 = min(dy + dh, my + mh)
                if ix < ix2 and iy < iy2:
                    inter = (ix2 - ix) * (iy2 - iy)
                    min_area = min(dw * dh, mw * mh)
                    if min_area > 0 and inter / min_area > 0.3:
                        already_found = True
                        break

            if not already_found:
                # Crop com margem e resize para ArcFace
                margin = int(max(dw, dh) * 0.2)
                cx = max(0, dx - margin)
                cy = max(0, dy - margin)
                cx2 = min(img_w, dx + dw + margin)
                cy2 = min(img_h, dy + dh + margin)
                crop = image_bgr[cy:cy2, cx:cx2]
                if crop.shape[0] > 20 and crop.shape[1] > 20:
                    face_112 = cv2.resize(crop, (112, 112))
                    embedding = _get_embedding(face_112)
                    faces.append({
                        "bbox_x": dx,
                        "bbox_y": dy,
                        "bbox_width": dw,
                        "bbox_height": dh,
                        "encoding": embedding,
                    })

        return faces

    except Exception as e:
        logger.error(f"Erro ao detectar rostos em {filepath}: {e}")
        return []


def find_matching_person(encoding: np.ndarray, db: Session) -> Optional[tuple[Person, float]]:
    """
    Busca pessoa conhecida que corresponde ao encoding fornecido.
    Usa APENAS rostos confirmados pelo usuário como referência.
    Compara por similaridade cosseno (ArcFace embeddings).
    Retorna (Person, confidence) ou None.
    """
    confirmed_faces = db.query(Face).filter(
        Face.person_id.isnot(None),
        Face.is_confirmed == True,
        Face.encoding.isnot(None),
    ).all()

    if not confirmed_faces:
        return None

    # Agrupa encodings por pessoa
    person_encodings: dict[int, list[np.ndarray]] = {}
    for face in confirmed_faces:
        try:
            enc = pickle.loads(face.encoding)
            if face.person_id not in person_encodings:
                person_encodings[face.person_id] = []
            person_encodings[face.person_id].append(enc)
        except Exception:
            continue

    # Compara com cada pessoa (similaridade cosseno)
    best_match = None
    best_similarity = SIMILARITY_THRESHOLD

    for person_id, encodings in person_encodings.items():
        similarities = [_cosine_similarity(encoding, enc) for enc in encodings]
        max_similarity = max(similarities)

        if max_similarity > best_similarity:
            best_similarity = max_similarity
            person = db.query(Person).get(person_id)
            if person:
                best_match = (person, max_similarity)

    return best_match


def process_faces_in_media(media: Media, db: Session) -> list[Face]:
    """
    Detecta e processa rostos em uma mídia.
    """
    filepath = media.organized_path or media.original_path

    if media.media_type != "image":
        return []

    detected = detect_faces_in_image(filepath)
    if not detected:
        return []

    faces_created = []

    for face_data in detected:
        encoding = face_data["encoding"]
        encoding_bytes = pickle.dumps(encoding)

        face = Face(
            bbox_x=face_data["bbox_x"],
            bbox_y=face_data["bbox_y"],
            bbox_width=face_data["bbox_width"],
            bbox_height=face_data["bbox_height"],
            encoding=encoding_bytes,
        )

        # Tenta sugerir pessoa (apenas com base em rostos confirmados)
        match = find_matching_person(encoding, db)
        if match:
            person, confidence = match
            face.person_id = person.id
            face.confidence = confidence
            face.is_confirmed = False  # Sugestão - aguarda aprovação

        db.add(face)
        db.flush()

        face.media_items.append(media)
        faces_created.append(face)

    db.commit()
    logger.info(f"Detectados {len(faces_created)} rostos em {filepath}")
    return faces_created


def cluster_unknown_faces(db: Session) -> dict:
    """
    Agrupa rostos não identificados em clusters usando DBSCAN.
    Usa distância cosseno (1 - similaridade) para clustering.
    NÃO cria pessoas — apenas retorna os agrupamentos para visualização.
    O usuário decide quem é quem manualmente.
    """
    unknown_faces = db.query(Face).filter(
        Face.person_id.is_(None),
        Face.encoding.isnot(None),
    ).all()

    if len(unknown_faces) < 2:
        return {"clusters": [], "noise": []}

    encodings = []
    valid_faces = []
    for face in unknown_faces:
        try:
            enc = pickle.loads(face.encoding)
            if np.linalg.norm(enc) > 0:
                encodings.append(enc)
                valid_faces.append(face)
        except Exception:
            continue

    if len(encodings) < 2:
        return {"clusters": [], "noise": []}

    encodings_array = np.array(encodings)

    # Normaliza para usar distância cosseno
    norms = np.linalg.norm(encodings_array, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = encodings_array / norms

    clustering = DBSCAN(
        eps=(1.0 - SIMILARITY_THRESHOLD),  # Converte threshold de similaridade para distância
        min_samples=2,
        metric="cosine",
    ).fit(normalized)

    labels = clustering.labels_
    unique_labels = set(labels)
    unique_labels.discard(-1)

    # Retorna agrupamentos sem criar pessoas
    clusters = []
    for label in unique_labels:
        face_ids = [valid_faces[i].id for i, l in enumerate(labels) if l == label]
        clusters.append(face_ids)

    noise_ids = [valid_faces[i].id for i, l in enumerate(labels) if l == -1]

    logger.info(f"Clustering: {len(clusters)} grupos encontrados, {len(noise_ids)} rostos isolados")
    return {"clusters": clusters, "noise": noise_ids}


def assign_face_to_person(face_id: int, person_id: int, db: Session) -> None:
    """Confirma manualmente a identidade de um rosto e sugere em rostos similares."""
    face = db.query(Face).get(face_id)
    if face:
        face.person_id = person_id
        face.is_confirmed = True
        face.confidence = 1.0
        db.commit()

        # Auto-sugestão: varre rostos não identificados e sugere essa pessoa
        _propagate_suggestions(face, person_id, db)


def _propagate_suggestions(confirmed_face: Face, person_id: int, db: Session) -> int:
    """
    Após confirmar um rosto, compara com todos os rostos não identificados
    e sugere a mesma pessoa onde a similaridade for alta.
    """
    if not confirmed_face.encoding:
        return 0

    confirmed_encoding = pickle.loads(confirmed_face.encoding)

    # Busca rostos sem pessoa atribuída
    unassigned = db.query(Face).filter(
        Face.person_id.is_(None),
        Face.encoding.isnot(None),
        Face.id != confirmed_face.id,
    ).all()

    suggested = 0
    for face in unassigned:
        try:
            enc = pickle.loads(face.encoding)
            sim = _cosine_similarity(confirmed_encoding, enc)
            if sim >= SIMILARITY_THRESHOLD:
                face.person_id = person_id
                face.confidence = float(sim)
                face.is_confirmed = False  # Sugestão, aguarda aprovação
                suggested += 1
        except Exception:
            continue

    if suggested > 0:
        db.commit()
        logger.info(f"Auto-sugestão: {suggested} rostos sugeridos como pessoa {person_id}")

    return suggested


def create_person(name: str, db: Session) -> Person:
    """Cria uma nova pessoa."""
    person = Person(name=name, is_confirmed=True)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def merge_persons(keep_id: int, merge_id: int, db: Session) -> None:
    """Mescla duas pessoas, mantendo uma e reatribuindo rostos."""
    faces_to_update = db.query(Face).filter(Face.person_id == merge_id).all()
    for face in faces_to_update:
        face.person_id = keep_id

    person_to_delete = db.query(Person).get(merge_id)
    if person_to_delete:
        db.delete(person_to_delete)

    db.commit()


def create_manual_face(media: Media, bbox_x: int, bbox_y: int, bbox_width: int, bbox_height: int, db: Session) -> Optional[Face]:
    """
    Cria um rosto manualmente a partir de coordenadas selecionadas pelo usuário.
    Faz crop da região, gera embedding ArcFace, e salva no banco.
    """
    import os

    # Lê a imagem original
    filepath = media.organized_path or media.original_path
    if not filepath or not os.path.exists(filepath):
        return None

    image_bgr = cv2.imread(filepath)
    if image_bgr is None:
        return None

    img_h, img_w = image_bgr.shape[:2]

    # Valida coordenadas
    x = max(0, min(bbox_x, img_w - 1))
    y = max(0, min(bbox_y, img_h - 1))
    w = max(10, min(bbox_width, img_w - x))
    h = max(10, min(bbox_height, img_h - y))

    # Crop com margem para melhorar embedding
    margin = int(max(w, h) * 0.1)
    cx = max(0, x - margin)
    cy = max(0, y - margin)
    cx2 = min(img_w, x + w + margin)
    cy2 = min(img_h, y + h + margin)
    crop = image_bgr[cy:cy2, cx:cx2]

    if crop.shape[0] < 10 or crop.shape[1] < 10:
        return None

    # Resize para 112x112 e gera embedding
    face_112 = cv2.resize(crop, (112, 112))
    embedding = _get_embedding(face_112)

    encoding_bytes = pickle.dumps(embedding)

    face = Face(
        bbox_x=x,
        bbox_y=y,
        bbox_width=w,
        bbox_height=h,
        encoding=encoding_bytes,
    )
    db.add(face)
    db.flush()
    face.media_items.append(media)

    # Tenta sugerir pessoa (se já tiver confirmados)
    match = find_matching_person(embedding, db)
    if match:
        person, confidence = match
        face.person_id = person.id
        face.confidence = confidence
        face.is_confirmed = False

    db.commit()
    return face
