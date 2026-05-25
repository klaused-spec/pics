"""
Serviço de detecção de duplicatas.
Usa SHA256 (exato) e perceptual hash (visual) para identificar duplicatas.
"""
import logging
from typing import Optional

import imagehash
from PIL import Image
import numpy as np
from sqlalchemy.orm import Session

from app.models import Media

logger = logging.getLogger(__name__)

# Limiar de similaridade para perceptual hash (quanto menor, mais similar)
PHASH_THRESHOLD = 8


def compute_perceptual_hash(filepath: str) -> Optional[str]:
    """
    Calcula o perceptual hash (pHash) de uma imagem.
    Robusto contra redimensionamento, compressão e pequenas edições.
    """
    try:
        with Image.open(filepath) as img:
            phash = imagehash.phash(img, hash_size=16)
            return str(phash)
    except Exception as e:
        logger.debug(f"Não foi possível calcular pHash de {filepath}: {e}")
        return None


def compute_average_hash(filepath: str) -> Optional[str]:
    """Calcula average hash como backup."""
    try:
        with Image.open(filepath) as img:
            ahash = imagehash.average_hash(img, hash_size=16)
            return str(ahash)
    except Exception:
        return None


def hamming_distance(hash1: str, hash2: str) -> int:
    """Calcula distância de Hamming entre dois hashes hexadecimais."""
    if not hash1 or not hash2:
        return 999

    h1 = imagehash.hex_to_hash(hash1)
    h2 = imagehash.hex_to_hash(hash2)
    return h1 - h2


def is_visual_duplicate(filepath: str, db: Session, threshold: int = PHASH_THRESHOLD) -> Optional[Media]:
    """
    Verifica se a imagem é visualmente duplicata de alguma já existente.
    Retorna o Media original se for duplicata, None caso contrário.
    """
    phash = compute_perceptual_hash(filepath)
    if not phash:
        return None

    # Busca candidatas no banco com perceptual hash similar
    # Primeiro busca exata
    exact_match = db.query(Media).filter(
        Media.perceptual_hash == phash,
        Media.is_duplicate == False,
    ).first()

    if exact_match:
        return exact_match

    # Busca aproximada - carrega todos os hashes e compara
    # (Em produção, usar uma estrutura de dados mais eficiente como VP-tree)
    all_media = db.query(Media).filter(
        Media.perceptual_hash.isnot(None),
        Media.is_duplicate == False,
    ).all()

    for media in all_media:
        distance = hamming_distance(phash, media.perceptual_hash)
        if distance <= threshold:
            logger.info(
                f"Duplicata visual detectada (distância={distance}): "
                f"{filepath} ~= {media.organized_path}"
            )
            return media

    return None


def check_duplicate(filepath: str, sha256_hash: str, db: Session) -> dict:
    """
    Verifica duplicatas usando múltiplos métodos.
    Retorna dict com resultado da verificação.
    """
    result = {
        "is_duplicate": False,
        "method": None,
        "duplicate_of_id": None,
        "confidence": 0.0,
    }

    # 1. Verificação por SHA256 (duplicata exata - 100% confiança)
    exact_match = db.query(Media).filter(
        Media.sha256_hash == sha256_hash,
        Media.is_duplicate == False,
    ).first()

    if exact_match:
        result["is_duplicate"] = True
        result["method"] = "sha256"
        result["duplicate_of_id"] = exact_match.id
        result["confidence"] = 1.0
        return result

    # 2. Verificação por perceptual hash (duplicata visual)
    visual_match = is_visual_duplicate(filepath, db)
    if visual_match:
        result["is_duplicate"] = True
        result["method"] = "perceptual_hash"
        result["duplicate_of_id"] = visual_match.id
        # Calcula confiança baseada na distância
        phash = compute_perceptual_hash(filepath)
        if phash and visual_match.perceptual_hash:
            distance = hamming_distance(phash, visual_match.perceptual_hash)
            result["confidence"] = max(0.0, 1.0 - (distance / PHASH_THRESHOLD))
        else:
            result["confidence"] = 0.8
        return result

    return result


def update_perceptual_hash(media: Media, db: Session) -> None:
    """Calcula e atualiza o perceptual hash de uma mídia."""
    if media.media_type != "image":
        return

    path = media.organized_path or media.original_path
    phash = compute_perceptual_hash(path)
    if phash:
        media.perceptual_hash = phash
        db.commit()
