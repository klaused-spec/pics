"""
Serviço de download de OneDrive (ou outros remotes) via rclone.

Baixa arquivos dos remotes configurados para o SOURCE_DIR, deixando que o
scan/organizador do pics organize e deduplique por SHA256 depois.

Dedup pré-download: para evitar baixar arquivos grandes (ex: vídeos de vários GB)
que já existem na biblioteca, consulta o banco (coluna `filename`) e gera uma
lista de exclusão para o rclone. Considera nomes de arquivo únicos na biblioteca
inteira (independente da pasta), conforme decisão do projeto.
"""
import os
import re
import json
import logging
import tempfile
import subprocess
from collections import deque
from datetime import datetime

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Media

logger = logging.getLogger(__name__)

# Buffer em memória com as últimas linhas de saída do rclone, para exibir o
# andamento na console web (endpoint GET /jobs/rclone-log).
_LOG_BUFFER: "deque[str]" = deque(maxlen=500)


def get_rclone_log() -> list[str]:
    """Retorna as últimas linhas de log do rclone (mais antigas primeiro)."""
    return list(_LOG_BUFFER)


def _log(line: str):
    """Loga e guarda a linha no buffer (com timestamp) para a web."""
    logger.info(f"[rclone] {line}")
    _LOG_BUFFER.append(f"{datetime.now().strftime('%H:%M:%S')} {line}")


def _get_existing_filenames() -> set[str]:
    """Retorna nomes de arquivo já presentes na biblioteca OU na lixeira.

    Inclui:
    - Banco de dados (Media.filename, excluindo duplicatas)
    - Arquivos em qualquer pasta .trash dentro de organized_dir e library_folders

    A comparação é case-insensitive (nomes normalizados para minúsculas), já que
    o rclone no Windows/OneDrive não diferencia maiúsculas de minúsculas.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(Media.filename)
            .filter(Media.is_duplicate == False)  # noqa: E712
            .all()
        )
        names = {r[0].lower() for r in rows if r[0]}
    finally:
        db.close()

    # Adiciona arquivos que estão na lixeira (não devem ser re-baixados)
    trash_dirs = []
    if settings.organized_dir:
        trash_dirs.append(os.path.join(settings.organized_dir, ".trash"))
    for folder in (settings.library_folders or []):
        trash_dirs.append(os.path.join(folder, ".trash"))

    for trash_dir in trash_dirs:
        if not os.path.isdir(trash_dir):
            continue
        try:
            for entry in os.scandir(trash_dir):
                if entry.is_file():
                    # Remove sufixo de deduplicação (_1, _2, ...) para casar o
                    # nome original do OneDrive (ex: foto_1.jpg -> foto.jpg)
                    stem, ext = os.path.splitext(entry.name.lower())
                    names.add(entry.name.lower())
                    # Também adiciona o nome sem o sufixo numérico (_N)
                    base = re.sub(r'_\d+$', '', stem)
                    if base != stem:
                        names.add(base + ext)
        except OSError:
            pass

    return names


def _write_exclude_file(filenames: set[str]) -> str | None:
    """Escreve um arquivo --exclude-from com um padrão por nome de arquivo.

    Retorna o caminho do arquivo temporário, ou None se não houver nada a excluir.
    O padrão do rclone é ancorado por nome (sem barra), então casa o arquivo em
    qualquer subpasta do remote.
    """
    if not filenames:
        return None

    fd, path = tempfile.mkstemp(prefix="rclone_exclude_", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for name in sorted(filenames):
                # Escapa caracteres especiais de glob do rclone: * ? [ ] { }
                escaped = (
                    name.replace("\\", "\\\\")
                    .replace("[", "\\[")
                    .replace("]", "\\]")
                    .replace("*", "\\*")
                    .replace("?", "\\?")
                    .replace("{", "\\{")
                    .replace("}", "\\}")
                )
                f.write(escaped + "\n")
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return path


def _run_rclone_copy(remote: str, src: str, dest: str, exclude_file: str | None,
                     on_line=None) -> int:
    """Executa `rclone copy` para uma pasta de um remote. Retorna o exit code.

    Faz streaming da saída do rclone (stats a cada 10s) para os logs, permitindo
    acompanhar o andamento em tempo real. `on_line`, se fornecido, recebe cada
    linha de status para reportar progresso.
    """
    os.makedirs(dest, exist_ok=True)

    source = f"{remote}:{src}" if src else f"{remote}:"
    args = [
        settings.rclone_path,
    ]
    if settings.rclone_config:
        args += ["--config", settings.rclone_config]
    args += [
        "copy",
        source,
        dest,
        "--transfers", str(settings.rclone_transfers),
        "--checkers", str(settings.rclone_checkers),
        # Flags de performance para OneDrive (configuráveis via .env)
        "--multi-thread-streams", str(settings.rclone_multi_thread_streams),
        "--buffer-size", settings.rclone_buffer_size,
        "--onedrive-chunk-size", settings.rclone_onedrive_chunk_size,
        "--ignore-existing",
        "--copy-links",
        "--stats", settings.rclone_stats_interval,
        "--stats-one-line",
        "--log-level", settings.rclone_log_level,
    ]
    if exclude_file:
        # --ignore-case: os nomes na lista de exclusão são normalizados para
        # minúsculas, mas os arquivos no OneDrive têm o case original (ex:
        # VID_...mp4). Sem isso o filtro não casa e o arquivo é rebaixado.
        args += ["--exclude-from", exclude_file, "--ignore-case"]

    _log(f"{source} -> {dest}")
    # stderr (onde o rclone escreve os stats/logs) redirecionado para stdout e
    # lido linha a linha para acompanhar o progresso em tempo real.
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            _log(line)
            if on_line:
                try:
                    on_line(line)
                except Exception:
                    pass
    finally:
        proc.stdout.close()
        code = proc.wait()

    if code != 0:
        logger.error(f"[rclone] saiu com código {code} para {source}")
    return code


def run_rclone_download(on_progress=None) -> dict:
    """Baixa todos os remotes/pastas configurados para o SOURCE_DIR.

    Retorna um dicionário com estatísticas: pastas processadas, erros e
    quantidade de nomes excluídos do download.

    `on_progress`, se fornecido, é chamado com (done, total, last_line) conforme
    cada pasta é concluída e a cada linha de status do rclone, permitindo
    acompanhar o andamento em tempo real (ex: atualizar um job na web).
    """
    if not settings.rclone_enabled:
        logger.info("[rclone] desativado (rclone_enabled=false); pulando.")
        return {"enabled": False, "folders": 0, "errors": 0, "excluded": 0}

    dest_base = settings.rclone_dest_dir or settings.source_dir
    remotes = settings.rclone_remotes

    if not remotes:
        logger.warning("[rclone] nenhum remote configurado (rclone_remotes vazio).")
        return {"enabled": True, "folders": 0, "errors": 0, "excluded": 0}

    # Total de pastas a processar (para a barra de progresso).
    total_folders = sum(len(entry["folders"] or [""]) for entry in remotes)

    existing = _get_existing_filenames()
    exclude_file = _write_exclude_file(existing)
    _log(f"{len(existing)} nomes excluídos do download (biblioteca + lixeira).")

    folders_done = 0
    errors = 0

    def _report(last_line: str = ""):
        if on_progress:
            try:
                on_progress(folders_done, total_folders, last_line)
            except Exception:
                pass

    _report("iniciando")
    try:
        for entry in remotes:
            remote = entry["remote"]
            name = entry["name"]
            folders = entry["folders"] or [""]
            for folder in folders:
                sub = folder.replace("/", os.sep)
                dest = os.path.join(dest_base, name, sub) if sub else os.path.join(dest_base, name)
                code = _run_rclone_copy(
                    remote, folder, dest, exclude_file,
                    on_line=lambda line: _report(line),
                )
                if code == 0:
                    folders_done += 1
                else:
                    errors += 1
                _log(f"{name}/{folder or '(raiz)'} concluído ({folders_done}/{total_folders})")
                _report(f"{name}/{folder or '(raiz)'} concluído")
    finally:
        if exclude_file:
            try:
                os.unlink(exclude_file)
            except OSError:
                pass

    return {
        "enabled": True,
        "folders": folders_done,
        "errors": errors,
        "excluded": len(existing),
        "total_folders": total_folders,
    }
