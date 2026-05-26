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

# Extensões que o browser NÃO toca nativamente
NON_WEB_EXTENSIONS = {".mpg", ".mpeg", ".avi", ".wmv", ".mkv", ".3gp", ".flv", ".ogv", ".webm", ".mov"}


def _get_duration(filepath: str) -> float:
    """Obtém duração do vídeo em segundos via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", filepath],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired, FileNotFoundError):
        return 0.0


def _write_progress(progress_file: str, percent: int):
    """Escreve percentual de progresso em arquivo."""
    try:
        with open(progress_file, "w") as f:
            f.write(str(percent))
    except OSError:
        pass


def get_transcode_progress(original_path: str) -> dict:
    """
    Retorna status de transcodificação de um vídeo.
    Returns: {"status": "idle"|"transcoding"|"done"|"error", "progress": 0-100}
    """
    transcoded_path = get_transcoded_path(original_path)
    progress_file = transcoded_path + ".progress"
    lock_file = transcoded_path + ".lock"

    if os.path.exists(transcoded_path):
        # Limpar arquivos auxiliares
        for f in [progress_file, lock_file]:
            if os.path.exists(f):
                os.remove(f)
        return {"status": "done", "progress": 100}

    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r") as f:
                pct = int(f.read().strip())
            if pct == -1:
                return {"status": "error", "progress": 0}
            return {"status": "transcoding", "progress": pct}
        except (ValueError, OSError):
            pass

    if os.path.exists(lock_file):
        return {"status": "transcoding", "progress": 0}

    return {"status": "idle", "progress": 0}


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
    Escreve progresso em arquivo .progress (0-100).
    Retorna o caminho do arquivo transcoded ou levanta exceção.
    """
    output_path = get_transcoded_path(original_path)
    progress_file = output_path + ".progress"

    if os.path.exists(output_path):
        logger.info(f"Transcoded já existe: {output_path}")
        return output_path

    # Obter duração total do vídeo via ffprobe
    total_duration = _get_duration(original_path)

    logger.info(f"Transcodificando: {original_path} (duração: {total_duration:.1f}s)")

    # Inicializar progresso
    _write_progress(progress_file, 0)

    try:
        # Usar -progress pipe:1 para ler progresso
        proc = subprocess.Popen(
            [
                "ffmpeg", "-i", original_path,
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                "-progress", "pipe:1",
                "-y",
                output_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Ler progresso do stdout
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_us="):
                try:
                    time_us = int(line.split("=")[1])
                    if total_duration > 0:
                        pct = min(99, int((time_us / 1_000_000) / total_duration * 100))
                        _write_progress(progress_file, pct)
                except (ValueError, ZeroDivisionError):
                    pass

        proc.wait(timeout=3600)

        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            if os.path.exists(output_path):
                os.remove(output_path)
            if os.path.exists(progress_file):
                os.remove(progress_file)
            logger.error(f"Erro ao transcodificar {original_path}: {stderr[-500:]}")
            raise RuntimeError(f"ffmpeg falhou: {stderr[-200:]}")

        _write_progress(progress_file, 100)
        # Limpar arquivo de progresso após conclusão
        if os.path.exists(progress_file):
            os.remove(progress_file)
        logger.info(f"Transcoded OK: {output_path} ({os.path.getsize(output_path) / 1024 / 1024:.1f} MB)")
        return output_path

    except subprocess.TimeoutExpired:
        if os.path.exists(output_path):
            os.remove(output_path)
        raise RuntimeError(f"Transcodificação timeout (1h): {original_path}")


def needs_transcode_check(media) -> bool:
    """Verifica se um vídeo precisa de transcodificação baseado no codec e extensão."""
    if media.video_codec and media.video_codec.lower() not in WEB_COMPATIBLE_CODECS:
        return True
    filepath = media.organized_path or media.original_path
    ext = Path(filepath).suffix.lower()
    if ext in NON_WEB_EXTENSIONS:
        return True
    return False


def get_playable_path(media) -> str:
    """
    Retorna o melhor caminho para streaming:
    - Se codec compatível e extensão web, retorna o original
    - Se já existe transcoded, retorna ele
    - Senão, transcodifica agora e retorna
    """
    filepath = media.organized_path or media.original_path

    # Verifica pela extensão também, não só pelo campo do banco
    if not needs_transcode_check(media):
        return filepath

    transcoded = get_transcoded_path(filepath)
    if os.path.exists(transcoded):
        return transcoded

    # Transcodificar sob demanda
    return transcode_video(filepath)
