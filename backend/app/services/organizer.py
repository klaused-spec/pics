"""
Serviço de organização de arquivos.
Escaneia a pasta de origem (OneDrive) e organiza os arquivos por ano/mês/dia.
"""
import os
import re
import shutil
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

import exifread
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Media

logger = logging.getLogger(__name__)

# Padrão de nome de arquivo com data: 20260101_153500.jpg / IMG_20260101_153500.jpg
DATE_PATTERNS = [
    re.compile(r"(\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})"),
    re.compile(r"(\d{4})-(\d{2})-(\d{2})[_\s](\d{2})[:\.](\d{2})[:\.](\d{2})"),
    re.compile(r"IMG[_-](\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})"),
    re.compile(r"VID[_-](\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})"),
    re.compile(r"PXL[_-](\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})"),
]


def extract_exif_date(filepath: str) -> Optional[datetime]:
    """Extrai data EXIF de uma imagem."""
    try:
        with open(filepath, "rb") as f:
            tags = exifread.process_file(f, stop_tag="DateTimeOriginal", details=False)

        date_tag = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
        if date_tag:
            date_str = str(date_tag)
            return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
    except Exception as e:
        logger.debug(f"Não foi possível ler EXIF de {filepath}: {e}")
    return None


def extract_date_from_filename(filename: str) -> Optional[datetime]:
    """Extrai data do nome do arquivo usando padrões conhecidos."""
    for pattern in DATE_PATTERNS:
        match = pattern.search(filename)
        if match:
            groups = match.groups()
            try:
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                hour, minute, second = int(groups[3]), int(groups[4]), int(groups[5])
                return datetime(year, month, day, hour, minute, second)
            except (ValueError, IndexError):
                continue
    return None


def get_media_date(filepath: str) -> datetime:
    """
    Determina a data da mídia usando (em ordem de prioridade):
    1. Data EXIF
    2. Data extraída do nome do arquivo
    3. Data de modificação do arquivo
    """
    # Tenta EXIF primeiro
    ext = Path(filepath).suffix.lower()
    if ext in settings.image_extensions:
        exif_date = extract_exif_date(filepath)
        if exif_date:
            return exif_date

    # Tenta extrair do nome do arquivo
    filename = Path(filepath).name
    filename_date = extract_date_from_filename(filename)
    if filename_date:
        return filename_date

    # Usa data de modificação do arquivo
    mtime = os.path.getmtime(filepath)
    return datetime.fromtimestamp(mtime)


def compute_sha256(filepath: str) -> str:
    """Calcula hash SHA256 do arquivo."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_organized_path(filepath: str, organized_dir: str) -> str:
    """
    Determina o caminho organizado baseado na data.
    Estrutura: organized_dir/YYYY/MM - NomeMes/arquivo
    """
    media_date = get_media_date(filepath)
    month_names = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }

    year_dir = str(media_date.year)
    month_dir = f"{media_date.month:02d} - {month_names[media_date.month]}"

    filename = Path(filepath).name
    dest_path = os.path.join(organized_dir, year_dir, month_dir, filename)

    # Se já existe um arquivo com o mesmo nome, adiciona sufixo
    if os.path.exists(dest_path):
        base = Path(filepath).stem
        ext = Path(filepath).suffix
        counter = 1
        while os.path.exists(dest_path):
            dest_path = os.path.join(
                organized_dir, year_dir, month_dir,
                f"{base}_{counter}{ext}"
            )
            counter += 1

    return dest_path


def get_media_type(filepath: str) -> str:
    """Determina se é imagem ou vídeo pela extensão."""
    ext = Path(filepath).suffix.lower()
    if ext in settings.image_extensions:
        return "image"
    elif ext in settings.video_extensions:
        return "video"
    return "unknown"


def get_image_dimensions(filepath: str) -> tuple[Optional[int], Optional[int]]:
    """Retorna largura e altura de uma imagem."""
    try:
        with Image.open(filepath) as img:
            return img.width, img.height
    except Exception:
        return None, None


def get_video_metadata(filepath: str) -> dict:
    """Extrai metadados de vídeo usando ffprobe (duração, dimensões)."""
    import subprocess, json
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", filepath],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        duration = None
        width, height = None, None

        if "format" in data and "duration" in data["format"]:
            duration = float(data["format"]["duration"])

        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = stream.get("width")
                height = stream.get("height")
                if not duration and "duration" in stream:
                    duration = float(stream["duration"])
                break

        return {"duration": duration, "width": width, "height": height}
    except Exception as e:
        logger.debug(f"Erro ao ler metadados de vídeo {filepath}: {e}")
        return {"duration": None, "width": None, "height": None}


def generate_video_thumbnail(video_path: str, output_path: str) -> bool:
    """Gera thumbnail de vídeo extraindo frame a 2s (ou 10% da duração)."""
    import subprocess
    try:
        # Pega duração para calcular posição do frame
        meta = get_video_metadata(video_path)
        duration = meta.get("duration") or 10
        # Captura a 2s ou 10% da duração (o que for menor)
        seek_time = min(2.0, duration * 0.1)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        result = subprocess.run(
            ["ffmpeg", "-y", "-ss", str(seek_time), "-i", video_path,
             "-vframes", "1", "-q:v", "3", output_path],
            capture_output=True, timeout=30,
        )
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception as e:
        logger.debug(f"Erro ao gerar thumbnail de vídeo: {e}")
        return False


def scan_source_directory(db: Session) -> list[str]:
    """
    Escaneia o diretório de origem e retorna arquivos novos (não processados).
    """
    source_dir = settings.source_dir
    new_files = []

    if not os.path.exists(source_dir):
        logger.error(f"Diretório de origem não encontrado: {source_dir}")
        return new_files

    for root, _dirs, files in os.walk(source_dir):
        for filename in files:
            filepath = os.path.join(root, filename)
            ext = Path(filepath).suffix.lower()

            if ext not in settings.all_extensions:
                continue

            # Verifica se já foi processado
            existing = db.query(Media).filter(Media.original_path == filepath).first()
            if existing:
                continue

            new_files.append(filepath)

    logger.info(f"Encontrados {len(new_files)} arquivos novos em {source_dir}")
    return new_files


def organize_file(filepath: str, db: Session) -> Optional[Media]:
    """
    Processa e organiza um único arquivo.
    Retorna o objeto Media criado ou None se for duplicata.
    """
    # Calcula hash
    file_hash = compute_sha256(filepath)

    # Verifica duplicata por hash
    existing = db.query(Media).filter(Media.sha256_hash == file_hash).first()
    if existing:
        logger.info(f"Duplicata detectada: {filepath} == {existing.organized_path}")
        # Registra como duplicata
        media = Media(
            original_path=filepath,
            filename=Path(filepath).name,
            media_type=get_media_type(filepath),
            sha256_hash=file_hash,
            is_duplicate=True,
            duplicate_of_id=existing.id,
            date_taken=get_media_date(filepath),
        )
        db.add(media)
        db.commit()
        return media

    # Determina destino
    dest_path = get_organized_path(filepath, settings.organized_dir)

    # Cria diretórios se necessário
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    # Copia arquivo (mantém original no OneDrive)
    shutil.copy2(filepath, dest_path)

    # Obtém dimensões e metadados
    width, height = None, None
    duration = None
    media_type = get_media_type(filepath)
    if media_type == "image":
        width, height = get_image_dimensions(dest_path)
    elif media_type == "video":
        meta = get_video_metadata(dest_path)
        width, height = meta.get("width"), meta.get("height")
        duration = meta.get("duration")
        # Gera thumbnail do vídeo
        thumb_dir = os.path.join(settings.organized_dir, ".thumbnails", "videos")
        thumb_path = os.path.join(thumb_dir, f"{Path(filepath).stem}.jpg")
        generate_video_thumbnail(dest_path, thumb_path)

    # Cria registro no banco
    media_date = get_media_date(filepath)
    media = Media(
        original_path=filepath,
        organized_path=dest_path,
        filename=Path(filepath).name,
        media_type=media_type,
        sha256_hash=file_hash,
        date_taken=media_date,
        date_file=datetime.fromtimestamp(os.path.getmtime(filepath)),
        width=width,
        height=height,
        duration_seconds=duration,
        is_organized=True,
    )
    db.add(media)
    db.commit()
    db.refresh(media)

    logger.info(f"Organizado: {filepath} -> {dest_path}")
    return media
