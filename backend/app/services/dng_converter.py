"""
Conversão de arquivos .dng (DNG) em .jpg de alta resolução.

Os .dng do Android/Samsung normalmente são DNG/TIFF com dados comprimidos em
JPEG XL (COMPRESSION.JPEGXL_DNG), photometric LinearRaw. rawpy/LibRaw e PIL não
os decodificam; usamos tifffile + imagecodecs.

O .jpg gerado fica ao lado do .dng (mesmo nome, extensão trocada) para que o
scan do pics o indexe normalmente — .dng não é uma extensão reconhecida. A data
de modificação do arquivo original é preservada.

Se as libs (tifffile/imagecodecs) não estiverem instaladas, a conversão é
ignorada silenciosamente (log de aviso) para não quebrar o scan.
"""
import os
import glob
import logging

logger = logging.getLogger(__name__)

JPEG_QUALITY = 95  # alta qualidade


def _build_srgb_lut(hi: float):
    """LUT uint8 (índice = valor linear original uint16) -> sRGB 8-bit.

    Evita processar o array inteiro em float32 (economia de memória para
    imagens grandes, ex.: 16320x12240 = 200 MP).
    """
    import numpy as np

    n = 65536  # cobre uint16
    x = np.arange(n, dtype=np.float32)
    x = np.clip(x / hi, 0.0, 1.0)
    srgb = np.where(
        x <= 0.0031308,
        x * 12.92,
        1.055 * np.power(x, 1 / 2.4) - 0.055,
    )
    return (np.clip(srgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def _to_8bit_srgb(arr):
    """Normaliza array (uint16 linear) para uint8 sRGB via LUT (baixo uso de RAM)."""
    import numpy as np

    if arr.dtype == np.uint8:
        return arr

    flat = arr.reshape(-1)
    sample = flat[:: max(1, flat.size // 2_000_000)]
    hi = float(np.percentile(sample, 99.5))
    if hi <= 0:
        hi = float(arr.max()) or 1.0

    idx = np.clip(arr, 0, 65535).astype(np.uint16)
    lut = _build_srgb_lut(hi)
    return lut[idx]


def convert_dng_file(dng_path: str) -> str | None:
    """Converte um .dng em .jpg ao lado. Retorna o caminho do .jpg ou None se pulado/erro."""
    import tifffile
    import imageio.v3 as iio

    jpg_path = os.path.splitext(dng_path)[0] + ".jpg"
    if os.path.exists(jpg_path):
        return None

    try:
        arr = tifffile.imread(dng_path)
        rgb = _to_8bit_srgb(arr)
        iio.imwrite(jpg_path, rgb, quality=JPEG_QUALITY)

        # Preserva a data de modificação do arquivo original
        st = os.stat(dng_path)
        os.utime(jpg_path, (st.st_atime, st.st_mtime))

        h, w = rgb.shape[:2]
        logger.info(f"[dng] convertido {os.path.basename(dng_path)} -> {os.path.basename(jpg_path)} ({w}x{h})")
        return jpg_path
    except Exception as e:
        logger.error(f"[dng] falha ao converter {dng_path}: {e}")
        # Remove um .jpg parcial que possa ter ficado
        try:
            if os.path.exists(jpg_path) and os.path.getsize(jpg_path) == 0:
                os.remove(jpg_path)
        except Exception:
            pass
        return None


def convert_dng_in_dir(base_dir: str) -> int:
    """Converte todos os .dng sob base_dir que ainda não têm .jpg correspondente.

    Retorna a quantidade de arquivos convertidos. Se as libs não estiverem
    disponíveis, retorna 0 sem quebrar.
    """
    if not base_dir or not os.path.isdir(base_dir):
        return 0

    try:
        import tifffile  # noqa: F401
        import imageio  # noqa: F401
    except ImportError:
        logger.warning("[dng] tifffile/imageio não instalados; conversão de .dng ignorada.")
        return 0

    files = glob.glob(os.path.join(base_dir, "**", "*.dng"), recursive=True)
    files += [f for f in glob.glob(os.path.join(base_dir, "**", "*.DNG"), recursive=True)
              if f not in files]

    if not files:
        return 0

    converted = 0
    for f in files:
        if convert_dng_file(f):
            converted += 1

    if converted:
        logger.info(f"[dng] {converted} arquivo(s) .dng convertido(s) em {base_dir}")
    return converted
