"""
HLS on-the-fly: gera segmentos .ts e playlist .m3u8 sob demanda via ffmpeg.

Fluxo:
  1. Cliente pede /api/media/{id}/hls/playlist.m3u8
  2. Backend consulta a duração do vídeo via ffprobe e gera a playlist com N segmentos.
  3. Cliente pede cada segmento /api/media/{id}/hls/seg_{n}.ts
  4. Backend invoca ffmpeg com -ss {start} -t {SEG_DURATION} e faz pipe do .ts para o response.

Nenhum arquivo é gravado em disco — tudo em memória/pipe.
ffmpeg usa -preset ultrafast para transcodificar em tempo real.
"""
import subprocess
import logging
from typing import Generator

from app.core.config import settings

logger = logging.getLogger(__name__)

SEG_DURATION = 4        # segundos por segmento
TARGET_HEIGHT = 720     # altura máxima (largura proporcional)
VIDEO_BITRATE = "2000k" # bitrate de vídeo
AUDIO_BITRATE = "128k"  # bitrate de áudio


def get_duration(filepath: str) -> float:
    """Retorna duração do vídeo em segundos via ffprobe."""
    try:
        result = subprocess.run(
            [
                settings.ffprobe_path,
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filepath,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"ffprobe falhou para {filepath}: {e}")
        return 0.0


def build_playlist(media_id: int, duration: float, base_url: str, token: str) -> str:
    """Gera o conteúdo da playlist HLS (.m3u8)."""
    import math
    n_segments = math.ceil(duration / SEG_DURATION)
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{SEG_DURATION}",
        "#EXT-X-MEDIA-SEQUENCE:0",
    ]
    for i in range(n_segments):
        seg_dur = min(SEG_DURATION, duration - i * SEG_DURATION)
        seg_url = f"{base_url}/api/media/{media_id}/hls/seg_{i}.ts?token={token}"
        lines.append(f"#EXTINF:{seg_dur:.3f},")
        lines.append(seg_url)
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines)


def stream_segment(filepath: str, seg_index: int) -> Generator[bytes, None, None]:
    """Gera e faz pipe do segmento .ts via ffmpeg (sem gravar em disco).

    Usa -ss exato (input seeking) para pular direto ao segundo certo — o ffmpeg
    lê apenas os bytes necessários do arquivo original, independente do tamanho.
    """
    start = seg_index * SEG_DURATION

    cmd = [
        settings.ffmpeg_path,
        "-ss", str(start),           # seek no input (rápido)
        "-i", filepath,
        "-t", str(SEG_DURATION),     # duração do segmento
        # Sem transcodificação: copia streams originais direto para MPEG-TS
        "-c", "copy",
        "-f", "mpegts",
        "-",                         # stdout
    ]

    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        while True:
            chunk = proc.stdout.read(64 * 1024)  # 64 KB
            if not chunk:
                break
            yield chunk
    except GeneratorExit:
        pass
    finally:
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait()
