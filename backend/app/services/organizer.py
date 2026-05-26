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
from app.models import Media, Face, media_faces

logger = logging.getLogger(__name__)


def move_to_trash(filepath: str) -> str:
    """Move arquivo para o trash ao invés de deletar. Retorna o novo caminho."""
    trash_dir = settings.trash_dir
    os.makedirs(trash_dir, exist_ok=True)
    filename = Path(filepath).name
    dest = os.path.join(trash_dir, filename)
    # Se já existe no trash, adiciona sufixo
    if os.path.exists(dest):
        base = Path(filepath).stem
        ext = Path(filepath).suffix
        counter = 1
        while os.path.exists(dest):
            dest = os.path.join(trash_dir, f"{base}_{counter}{ext}")
            counter += 1
    shutil.move(filepath, dest)
    logger.info(f"Movido para trash: {filepath} -> {dest}")
    return dest

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
    """Calcula hash SHA256 do arquivo. Para arquivos >100MB, usa hash parcial (primeiro+último 4MB + tamanho)."""
    file_size = os.path.getsize(filepath)
    sha256 = hashlib.sha256()

    if file_size > 100 * 1024 * 1024:  # >100MB: hash parcial para performance
        chunk_size = 4 * 1024 * 1024  # 4MB
        sha256.update(str(file_size).encode())  # Inclui tamanho no hash
        with open(filepath, "rb") as f:
            sha256.update(f.read(chunk_size))  # Primeiro 4MB
            f.seek(max(0, file_size - chunk_size))
            sha256.update(f.read(chunk_size))  # Último 4MB
    else:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)

    return sha256.hexdigest()


def get_organized_path(filepath: str, organized_dir: str) -> str:
    """
    Determina o caminho organizado baseado na data e padrão configurado.
    Padrões:
      - "year/month": organized_dir/YYYY/MM/arquivo
      - "year_month": organized_dir/YYYY_MM/arquivo
    """
    media_date = get_media_date(filepath)
    pattern = settings.organization_pattern

    if pattern == "year_month":
        # Padrão flat: YYYY_MM/
        subfolder = f"{media_date.year}_{media_date.month:02d}"
        dest_dir = os.path.join(organized_dir, subfolder)
    else:
        # Padrão hierárquico (default): YYYY/MM/
        year_dir = str(media_date.year)
        month_dir = f"{media_date.month:02d}"
        dest_dir = os.path.join(organized_dir, year_dir, month_dir)

    filename = Path(filepath).name
    dest_path = os.path.join(dest_dir, filename)

    # Se já existe um arquivo com o mesmo nome, adiciona sufixo
    if os.path.exists(dest_path):
        base = Path(filepath).stem
        ext = Path(filepath).suffix
        counter = 1
        while os.path.exists(dest_path):
            dest_path = os.path.join(dest_dir, f"{base}_{counter}{ext}")
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
    """Extrai metadados de vídeo usando ffprobe (duração, dimensões, codec)."""
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
        codec = None

        if "format" in data and "duration" in data["format"]:
            duration = float(data["format"]["duration"])

        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = stream.get("width")
                height = stream.get("height")
                codec = stream.get("codec_name")
                if not duration and "duration" in stream:
                    duration = float(stream["duration"])
                break

        return {"duration": duration, "width": width, "height": height, "codec": codec}
    except Exception as e:
        logger.debug(f"Erro ao ler metadados de vídeo {filepath}: {e}")
        return {"duration": None, "width": None, "height": None, "codec": None}


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
    Também move arquivos que já foram processados mas ainda estão no source.
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

            # Verifica se já foi processado (por path)
            existing = db.query(Media).filter(Media.original_path == filepath).first()
            if existing:
                # Confirma que é realmente o mesmo arquivo (hash)
                file_hash = compute_sha256(filepath)
                if file_hash != existing.sha256_hash:
                    # Mesmo path mas conteúdo diferente = arquivo novo (ex: IMG001.jpg de outra câmera)
                    logger.info(f"Arquivo novo no mesmo path (hash diferente): {filepath}")
                    new_files.append(filepath)
                    continue

                # Já está no banco — se já tem organized_path diferente, o arquivo no source é sobra
                if existing.organized_path and existing.organized_path != filepath and os.path.exists(existing.organized_path):
                    # O organizado já existe, mover sobra para trash
                    move_to_trash(filepath)
                elif existing.organized_path and existing.organized_path != filepath and not os.path.exists(existing.organized_path):
                    # O organizado sumiu, mover de novo
                    new_files.append(filepath)
                else:
                    # original_path == organized_path == filepath (nunca foi movido)
                    new_files.append(filepath)
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

    # Verifica se este arquivo já está no banco (por path E hash)
    existing_self = db.query(Media).filter(
        Media.original_path == filepath,
        Media.sha256_hash == file_hash
    ).first()
    if existing_self:
        if existing_self.organized_path == filepath:
            # Nunca foi movido — mover agora
            dest_path = get_organized_path(filepath, settings.organized_dir)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.move(filepath, dest_path)
            existing_self.organized_path = dest_path
            existing_self.is_organized = True
            db.commit()
            logger.info(f"Movido (re-org): {filepath} -> {dest_path}")
            return existing_self
        elif existing_self.organized_path and not os.path.exists(existing_self.organized_path):
            # O organized foi deletado — re-mover do source
            dest_path = get_organized_path(filepath, settings.organized_dir)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.move(filepath, dest_path)
            existing_self.organized_path = dest_path
            existing_self.is_organized = True
            db.commit()
            logger.info(f"Re-movido (org deletado): {filepath} -> {dest_path}")
            return existing_self

    # Verifica duplicata por hash
    existing = db.query(Media).filter(Media.sha256_hash == file_hash).first()
    if existing:
        # Se o arquivo organizado do registro existente NÃO existe mais no disco,
        # isso é um re-org (usuário deletou organized e colocou de volta no source)
        if existing.organized_path and not os.path.exists(existing.organized_path):
            dest_path = get_organized_path(filepath, settings.organized_dir)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.move(filepath, dest_path)
            existing.organized_path = dest_path
            existing.original_path = filepath
            existing.is_organized = True
            db.commit()
            logger.info(f"Re-organizado (hash match, org deletado): {filepath} -> {dest_path}")
            return existing

        logger.info(f"Duplicata detectada: {filepath} == {existing.organized_path}")
        # Registra como duplicata e remove do source
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
        # Move arquivo duplicado para trash (nunca deletar)
        move_to_trash(filepath)
        return media

    # Determina destino
    dest_path = get_organized_path(filepath, settings.organized_dir)

    # Cria diretórios se necessário
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    # Move arquivo do source para organizado
    shutil.move(filepath, dest_path)

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
    media_date = get_media_date(dest_path)
    media = Media(
        original_path=filepath,
        organized_path=dest_path,
        filename=Path(filepath).name,
        media_type=media_type,
        sha256_hash=file_hash,
        date_taken=media_date,
        date_file=datetime.fromtimestamp(os.path.getmtime(dest_path)),
        width=width,
        height=height,
        duration_seconds=duration,
        is_organized=True,
    )
    db.add(media)
    db.commit()
    db.refresh(media)

    # Re-linkar faces órfãs que pertencem a este conteúdo (por sha256)
    orphan_faces = db.query(Face).filter(Face.media_sha256 == file_hash).all()
    for face in orphan_faces:
        if media not in face.media_items:
            face.media_items.append(media)
    if orphan_faces:
        db.commit()
        logger.info(f"Re-linkadas {len(orphan_faces)} faces ao media {filepath}")

    # Restaurar dados de IA do cache (AiCache)
    from app.models import AiCache
    cached_ai = db.query(AiCache).filter(AiCache.sha256_hash == file_hash).first()
    if cached_ai:
        media.ai_description = cached_ai.ai_description
        media.ai_location = cached_ai.ai_location
        media.ai_scene_type = cached_ai.ai_scene_type
        media.ai_objects = cached_ai.ai_objects
        media.ai_processed = True
        media.ai_processed_at = cached_ai.processed_at
        db.commit()
        logger.info(f"Restaurado cache AI para {filepath}")

    logger.info(f"Organizado: {filepath} -> {dest_path}")
    return media
