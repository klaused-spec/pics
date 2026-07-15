"""
Serviço para detectar e recuperar mount points stale (WSL specific).
Quando um HD externo é desplugado, a montagem em /mnt/X fica "stale" e inacessível.
Este serviço:
1. Detecta quando um mount está stale
2. Tenta remontar automaticamente
3. Avisa se o problema persiste
"""
import os
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def is_mount_stale(mount_path: str) -> bool:
    """
    Verifica se um mount point está acessível (não stale).
    Retorna True se está stale (inacessível), False se OK.
    """
    if not os.path.exists(mount_path):
        logger.debug(f"Mount point não existe: {mount_path}")
        return True
    
    try:
        # Tenta acessar com timeout curto (2s)
        result = subprocess.run(
            ["timeout", "2", "ls", "-la", mount_path],
            capture_output=True,
            timeout=3,
        )
        # Se retornar sucesso, não está stale
        return result.returncode != 0
    except Exception as e:
        logger.warning(f"Erro ao verificar mount {mount_path}: {e}")
        return True


def try_remount(mount_path: str, drive_letter: str) -> bool:
    """
    Tenta desmontar e remontar um drive no WSL.
    Exemplo: try_remount('/mnt/g', 'G')
    Retorna True se conseguiu remontar, False se falhou.
    """
    try:
        logger.info(f"Tentando remontar {mount_path}...")
        
        # Tenta desmontar
        subprocess.run(
            ["sudo", "umount", mount_path],
            capture_output=True,
            timeout=5,
        )
        logger.debug(f"Desmontado: {mount_path}")
        
        # Aguarda um pouco
        import time
        time.sleep(1)
        
        # Tenta remontar
        result = subprocess.run(
            ["sudo", "mount", "-t", "drvfs", f"{drive_letter}:", mount_path],
            capture_output=True,
            timeout=5,
        )
        
        if result.returncode == 0:
            logger.info(f"✓ Remontado com sucesso: {mount_path}")
            return True
        else:
            logger.warning(f"✗ Falha ao remontar {mount_path}: {result.stderr.decode()}")
            return False
            
    except Exception as e:
        logger.error(f"Erro ao remontar {mount_path}: {e}")
        return False


def check_and_recover_library_mounts(library_folders: list[str]) -> dict:
    """
    Verifica todos os library_folders e tenta recuperar os que estão stale.
    Retorna um dict com status de cada pasta.
    """
    results = {}
    
    for folder in library_folders:
        # Filtra apenas mounts /mnt/X (WSL specific)
        if not folder.startswith("/mnt/"):
            results[folder] = {"status": "not_wsl_mount", "recovered": False}
            continue
        
        # Extrai letra do drive (ex: /mnt/g -> G)
        try:
            drive_letter = folder.split("/")[-1].upper()
        except:
            results[folder] = {"status": "invalid_path", "recovered": False}
            continue
        
        # Verifica se está stale
        if is_mount_stale(folder):
            logger.warning(f"⚠ Mount stale detectado: {folder}")
            results[folder] = {
                "status": "stale",
                "recovered": try_remount(folder, drive_letter),
            }
        else:
            results[folder] = {"status": "ok", "recovered": False}
    
    return results


def get_mount_status(folder: str) -> str:
    """
    Retorna status legível de um mount point.
    """
    if not folder.startswith("/mnt/"):
        return "not_mounted"
    
    if is_mount_stale(folder):
        return "stale"
    
    return "ok"
