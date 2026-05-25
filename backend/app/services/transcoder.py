"""
Serviço de transcodificação de vídeo sob demanda.
Converte vídeos com codecs incompatíveis para H.264/AAC MP4.
O arquivo transcoded fica na mesma pasta com sufixo _transcoded.mp4
"""
import os
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Codecs que o browser toca nativamente
WEB_COMPATIBLE_CODECS = {"h264", "hevc", "vp8", "vp9", "av1"}


def get_transcoded_path(original_path: str) -> str:
    """Retorna o caminho do arquivo transcoded para um vídeo."""
    p = Path(original_path)
    return str(p.parent / f"{p.stem}_transcoded.mp4")


def is_transcoded(original_path: str) -> bool:
    """Verifica se já existe versão transcoded."""
    return os.path.exists(get_transcoded_path(original_path))


def transcode_video(original_path: str) -> str:
    """
    Transcodifica vídeo para H.264/AAC MP4.
    Retorna o caminho do arquivo transcoded ou levanta exceção.
    """
    output_path = get_transcoded_path(original_path)

    if os.path.exists(output_path):
        logger.info(f"Transcoded já existe: {output_path}")
        return output_path

    logger.info(f"Transcodificando: {original_path}")

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-i", original_path,
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                "-y",
                output_path,
            ],
            capture_output=True, text=True, timeout=3600,
        )

        if result.returncode != 0:
            # Limpar arquivo parcial
            if os.path.exists(output_path):
                os.remove(output_path)
            logger.error(f"Erro ao transcodificar {original_path}: {result.stderr[-500:]}")
            raise RuntimeError(f"ffmpeg falhou: {result.stderr[-200:]}")

        logger.info(f"Transcoded OK: {output_path} ({os.path.getsize(output_path) / 1024 / 1024:.1f} MB)")
        return output_path

    except subprocess.TimeoutExpired:
        if os.path.exists(output_path):
            os.remove(output_path)
        raise RuntimeError(f"Transcodificação timeout (1h): {original_path}")


def get_playable_path(media) -> str:
    """
    Retorna o melhor caminho para streaming:
    - Se codec compatível, retorna o original
    - Se já existe transcoded, retorna ele
    - Senão, transcodifica agora e retorna
    """
    filepath = media.organized_path or media.original_path

    if not media.needs_transcode:
        return filepath

    transcoded = get_transcoded_path(filepath)
    if os.path.exists(transcoded):
        return transcoded

    # Transcodificar sob demanda
    return transcode_video(filepath)
