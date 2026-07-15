"""
Integração com Azure OpenAI para análise de imagens e vídeos.
Usa GPT-4 Vision para descrever cenas, identificar locais e objetos.
"""
import base64
import logging
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from openai import AzureOpenAI
from sqlalchemy.orm import Session
import datetime

from app.core.config import settings
from app.models import Media, Tag, AiCache

logger = logging.getLogger(__name__)


def get_openai_client() -> AzureOpenAI:
    """Cria cliente Azure OpenAI."""
    return AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_key,
        api_version=settings.azure_openai_api_version,
    )


def encode_image_base64(filepath: str) -> str:
    """Codifica imagem em base64 para envio à API."""
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def analyze_image(filepath: str) -> Optional[dict]:
    """
    Analisa uma imagem usando Azure OpenAI GPT-4 Vision.
    Retorna descrição, local, tipo de cena e objetos detectados.
    """
    try:
        client = get_openai_client()
        base64_image = encode_image_base64(filepath)

        ext = Path(filepath).suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp",
            ".gif": "image/gif", ".bmp": "image/bmp",
        }
        mime_type = mime_map.get(ext, "image/jpeg")

        response = client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[
                {
                    "role": "system",
                    "content": """Você é um assistente especializado em analisar fotos pessoais e familiares.
Analise a imagem e retorne um JSON com os seguintes campos:
- "description": Descrição detalhada da cena em português (2-3 frases)
- "location": Local provável onde a foto foi tirada (cidade, praia, parque, restaurante, etc.) ou "desconhecido"
- "scene_type": Tipo de cena (retrato, paisagem, grupo, selfie, evento, comida, animal, etc.)
- "objects": Lista de objetos/elementos principais visíveis
- "people_count": Número estimado de pessoas na foto
- "mood": Atmosfera/humor da foto (alegre, tranquilo, festivo, etc.)
- "season": Estação do ano aparente ou "indefinido"
- "indoor_outdoor": "interior" ou "exterior" ou "indefinido"
Retorne APENAS o JSON, sem markdown ou texto adicional."""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}",
                                "detail": "low"  # Usa resolução baixa para economizar tokens
                            }
                        }
                    ]
                }
            ],
            max_completion_tokens=500,
            temperature=0.3,
        )

        content = response.choices[0].message.content
        # Remove possível markdown wrapper
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]

        result = json.loads(content)
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Erro ao parsear resposta da IA para {filepath}: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro ao analisar imagem {filepath}: {e}")
        return None


def analyze_video_thumbnail(filepath: str) -> Optional[dict]:
    """
    Extrai um frame do vídeo e analisa usando GPT-4 Vision.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        thumb_png = os.path.join(temp_dir, f"{Path(filepath).stem}.thumb.png")
        thumb_jpg = os.path.join(temp_dir, f"{Path(filepath).stem}.thumb.jpg")
        thumb_path = thumb_png

        def run_extraction(cmd):
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )

        def log_ffmpeg_failure(stage: str, cmd, result):
            logger.error(
                "Erro ao analisar vídeo %s (%s): ffmpeg retornou código %s\n"
                "comando: %s\n"
                "stdout:\n%s\n"
                "stderr:\n%s",
                filepath,
                stage,
                result.returncode,
                " ".join(cmd),
                result.stdout.strip(),
                result.stderr.strip(),
            )
            logger.debug("ffmpeg full stdout: %s", result.stdout)
            logger.debug("ffmpeg full stderr: %s", result.stderr)

        try:
            Path(thumb_png).unlink(missing_ok=True)
            Path(thumb_jpg).unlink(missing_ok=True)
        except Exception:
            pass

        png_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            filepath,
            "-ss",
            "00:00:00.5",
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgb24",
            "-update",
            "1",
            "-y",
            thumb_png,
        ]

        jpg_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            filepath,
            "-ss",
            "00:00:00.5",
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-y",
            thumb_jpg,
        ]

        try:
            result = run_extraction(png_cmd)
            thumb_path = thumb_png
            if result.returncode != 0:
                logger.warning("PNG thumbnail extraction failed for %s, trying JPG fallback.", filepath)
                log_ffmpeg_failure("PNG extraction", png_cmd, result)

                result = run_extraction(jpg_cmd)
                thumb_path = thumb_jpg
                if result.returncode != 0:
                    log_ffmpeg_failure("JPG fallback", jpg_cmd, result)
                    return None

            if not Path(thumb_path).exists():
                logger.error("Thumbnail file not found after ffmpeg extraction: %s", thumb_path)
                return None

            result_data = analyze_image(thumb_path)
            if result_data is None and thumb_path == thumb_png:
                logger.warning("PNG thumbnail analysis failed for %s, retrying with JPG fallback.", filepath)
                Path(thumb_png).unlink(missing_ok=True)
                result = run_extraction(jpg_cmd)
                thumb_path = thumb_jpg
                if result.returncode != 0:
                    log_ffmpeg_failure("JPG retry", jpg_cmd, result)
                    return None
                if not Path(thumb_path).exists():
                    logger.error("Thumbnail file not found after JPG retry: %s", thumb_path)
                    return None
                result_data = analyze_image(thumb_path)

            return result_data
        except FileNotFoundError as e:
            logger.error(f"Erro ao analisar vídeo {filepath}: comando ffmpeg não encontrado: {e}")
            return None
        except subprocess.TimeoutExpired as e:
            logger.error("Timeout ao analisar vídeo %s: %s", filepath, e)
            return None
        except Exception as e:
            logger.exception("Erro inesperado ao analisar vídeo %s: %s", filepath, e)
            return None
        finally:
            try:
                Path(thumb_path).unlink(missing_ok=True)
            except Exception:
                pass


def process_media_ai(media: Media, db: Session) -> None:
    """
    Processa uma mídia com Azure OpenAI e atualiza o banco de dados.
    Reutiliza cache por SHA256 se já foi processado antes.
    """
    filepath = media.organized_path or media.original_path

    # Tenta reutilizar do cache (sobrevive a re-indexações)
    if media.sha256_hash:
        cached = db.query(AiCache).filter(AiCache.sha256_hash == media.sha256_hash).first()
        if cached and cached.ai_description:
            media.ai_description = cached.ai_description
            media.ai_location = cached.ai_location
            media.ai_scene_type = cached.ai_scene_type
            media.ai_objects = cached.ai_objects
            media.ai_processed = True
            media.ai_processed_at = cached.processed_at or datetime.datetime.utcnow()

            # Recria tags a partir do cache
            _apply_tags_from_result(media, {
                "scene_type": cached.ai_scene_type,
                "location": cached.ai_location,
                "objects": cached.ai_objects or [],
            }, db)
            db.commit()
            logger.info(f"IA (cache): {filepath}")
            return

    if media.media_type == "image":
        result = analyze_image(filepath)
    elif media.media_type == "video":
        result = analyze_video_thumbnail(filepath)
    else:
        return

    if not result:
        return

    # Atualiza o registro
    media.ai_description = result.get("description", "")
    media.ai_location = result.get("location", "")
    media.ai_scene_type = result.get("scene_type", "")
    media.ai_objects = result.get("objects", [])
    media.ai_processed = True
    media.ai_processed_at = datetime.datetime.utcnow()

    # Salva no cache por hash (sobrevive a reset do banco)
    if media.sha256_hash:
        cached = db.query(AiCache).filter(AiCache.sha256_hash == media.sha256_hash).first()
        if not cached:
            cached = AiCache(sha256_hash=media.sha256_hash)
            db.add(cached)
        cached.ai_description = media.ai_description
        cached.ai_location = media.ai_location
        cached.ai_scene_type = media.ai_scene_type
        cached.ai_objects = media.ai_objects
        cached.processed_at = media.ai_processed_at

    # Cria/associa tags
    _apply_tags_from_result(media, result, db)

    db.commit()
    logger.info(f"IA processou: {filepath} - {media.ai_description[:80]}...")


def _apply_tags_from_result(media: Media, result: dict, db: Session):
    """Cria/associa tags a partir do resultado de IA."""
    tag_sources = []
    if result.get("scene_type"):
        tag_sources.append(("scene", result["scene_type"]))
    if result.get("location") and result["location"] != "desconhecido":
        tag_sources.append(("location", result["location"]))
    if result.get("mood"):
        tag_sources.append(("mood", result["mood"]))
    if result.get("indoor_outdoor") and result["indoor_outdoor"] != "indefinido":
        tag_sources.append(("environment", result["indoor_outdoor"]))
    for obj in result.get("objects", [])[:5]:
        tag_sources.append(("object", obj))

    for category, name in tag_sources:
        tag = db.query(Tag).filter(Tag.name == name.lower()).first()
        if not tag:
            tag = Tag(name=name.lower(), category=category)
            db.add(tag)
            db.flush()
        if tag not in media.tags:
            media.tags.append(tag)


def search_by_description(query: str, db: Session, limit: int = 50) -> list[Media]:
    """
    Busca mídias por descrição, nome de arquivo, extensão e data.
    """
    import re
    query_lower = query.strip().lower()
    words = query_lower.split()

    base = db.query(Media).filter(
        Media.is_duplicate == False,
        Media.is_organized == True,
    )

    # Mapa de meses em português para número
    month_map = {
        "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
        "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
        "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
        "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
        "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
    }

    # Detecta padrão de data: "2013", "2013-07", "07/2013", "2013-07-15"
    date_match = re.match(r'^(\d{4})[-/]?(\d{1,2})?[-/]?(\d{1,2})?$', query_lower)
    if date_match:
        year = int(date_match.group(1))
        month = int(date_match.group(2)) if date_match.group(2) else None
        day = int(date_match.group(3)) if date_match.group(3) else None
        from sqlalchemy import func as sqlfunc
        base = base.filter(sqlfunc.extract("year", Media.date_taken) == year)
        if month:
            base = base.filter(sqlfunc.extract("month", Media.date_taken) == month)
        if day:
            base = base.filter(sqlfunc.extract("day", Media.date_taken) == day)
        return base.order_by(Media.date_taken.desc()).limit(limit).all()

    # Detecta padrão "dd/mm/yyyy"
    date_match2 = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', query_lower)
    if date_match2:
        from sqlalchemy import func as sqlfunc
        day = int(date_match2.group(1))
        month = int(date_match2.group(2))
        year = int(date_match2.group(3))
        base = base.filter(sqlfunc.extract("year", Media.date_taken) == year)
        base = base.filter(sqlfunc.extract("month", Media.date_taken) == month)
        base = base.filter(sqlfunc.extract("day", Media.date_taken) == day)
        return base.order_by(Media.date_taken.desc()).limit(limit).all()

    # Detecta nome de mês em português
    if query_lower in month_map:
        from sqlalchemy import func as sqlfunc
        base = base.filter(sqlfunc.extract("month", Media.date_taken) == month_map[query_lower])
        return base.order_by(Media.date_taken.desc()).limit(limit).all()

    # Detecta busca por extensão (.mp4, .jpg, mp4, jpg)
    ext_query = query_lower.lstrip(".")
    known_exts = {"jpg", "jpeg", "png", "gif", "bmp", "webp", "heic", "mp4", "mov", "avi", "mkv", "wmv", "mpeg", "mpg", "3gp", "webm"}
    if ext_query in known_exts:
        base = base.filter(Media.filename.ilike(f"%.{ext_query}"))
        return base.order_by(Media.date_taken.desc()).limit(limit).all()

    # Busca geral: nome do arquivo + descrição IA + localização + cena
    from sqlalchemy import or_
    for word in words:
        base = base.filter(
            or_(
                Media.filename.ilike(f"%{word}%"),
                Media.ai_description.ilike(f"%{word}%"),
                Media.ai_location.ilike(f"%{word}%"),
                Media.ai_scene_type.ilike(f"%{word}%"),
            )
        )

    return base.order_by(Media.date_taken.desc()).limit(limit).all()
