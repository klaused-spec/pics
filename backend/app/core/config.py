from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
from pathlib import Path
from typing import Any
import json
import os


class Settings(BaseSettings):
    # Autenticação JWT
    secret_key: str = "your-secret-key-change-in-production"  # MUDAR EM PRODUÇÃO
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 horas

    # Frontend - Domínio/hosts permitidos para CORS
    allowed_hosts: str = "localhost,127.0.0.1"  # Separado por vírgula
    frontend_port: int = 5173
    backend_port: int = 8000

    @property
    def allowed_hosts_list(self) -> list[str]:
        """Converte string de hosts para lista."""
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_key: str = ""
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_api_version: str = "2024-08-01-preview"
    ai_processing_enabled: bool = True

    # Diretórios
    source_dir: str = "/home/kkirner/src/pics/FOTOS/source"
    organized_dir: str = "/home/kkirner/src/pics/FOTOS/organized"

    # Organização
    # Padrão: "year/month" = YYYY/MM/  |  "year_month" = YYYY_MM[_descricao]/
    organization_pattern: str = "year/month"
    # Pastas de biblioteca adicionais (além de organized_dir) - separadas por vírgula no .env
    library_folders_raw: str = ""

    # Permitir modificar arquivos em library_folders (excluir, transcodificar)
    allow_library_modify: bool = False

    @property
    def library_folders(self) -> list[str]:
        if not self.library_folders_raw:
            return []
        return [f.strip() for f in self.library_folders_raw.split(",") if f.strip()]

    @library_folders.setter
    def library_folders(self, value: list[str]):
        self.library_folders_raw = ",".join(value)

    # rclone (download de OneDrive/outros remotes para o source_dir)
    rclone_enabled: bool = False
    rclone_path: str = "rclone"
    rclone_transfers: int = 8
    rclone_checkers: int = 16
    rclone_interval_minutes: int = 60
    # Destino dos downloads (vazio = usa source_dir)
    rclone_dest_dir: str = ""
    # Flags de performance do rclone (0 = deixa o rclone decidir)
    rclone_multi_thread_streams: int = 0
    rclone_buffer_size: str = "256M"
    rclone_onedrive_chunk_size: str = "10M"
    # Intervalo dos stats na saída (para acompanhar o progresso) e verbosidade
    rclone_stats_interval: str = "10s"
    rclone_log_level: str = "INFO"
    # Perfis em JSON: lista de objetos {name, remote, folders}
    # Ex: [{"name":"klauskirner","remote":"onedrive-klauskirner","folders":["Imagens","Pictures"]}]
    # folders vazio/ausente = conta inteira.
    rclone_remotes_raw: str = ""

    @property
    def rclone_remotes(self) -> list[dict]:
        if not self.rclone_remotes_raw:
            return []
        try:
            data = json.loads(self.rclone_remotes_raw)
        except (json.JSONDecodeError, TypeError):
            return []
        result = []
        for entry in data:
            name = (entry.get("name") or "").strip()
            if not name:
                continue
            remote = (entry.get("remote") or f"onedrive-{name}").strip()
            folders = [f.strip() for f in entry.get("folders", []) if f and f.strip()]
            result.append({"name": name, "remote": remote, "folders": folders})
        return result

    # Banco de dados
    # Pode ser sobrescrito no .env com DATABASE_URL=sqlite:///C:/caminho/absoluto/pics.db
    # O default usa caminho absoluto relativo a este arquivo para não depender do cwd.
    database_url: str = "sqlite:///" + str(Path(__file__).parent.parent.parent / "pics.db").replace("\\", "/")

    # Servidor
    host: str = "0.0.0.0"
    port: int = 8000

    # Processamento
    batch_size: int = 10
    max_concurrent_ai_calls: int = 3
    scan_interval_minutes: int = 30
    scheduler_enabled: bool = False
    scan_workers: int = 4  # Número de threads paralelas para scan (SHA256, metadados, pHash)
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"

    # Face detection / recognition tuning
    face_detection_min_confidence: float = 0.5
    face_mesh_min_detection_confidence: float = 0.5
    face_mesh_max_num_faces: int = 10
    face_detector_model_selection: int = 1
    face_dedup_iou_threshold: float = 0.5
    face_auto_approve_high_confidence: bool = False
    face_auto_approve_min_confidence: float = 0.75
    ort_log_severity: int = 3  # ONNX Runtime log severity (0=VERBOSE .. 4=FATAL)

    # Extensões suportadas
    image_extensions: list[str] = [
        ".jpg", ".jpeg", ".png", ".heic", ".heif",
        ".webp", ".tiff", ".tif", ".bmp", ".gif"
    ]
    video_extensions: list[str] = [
        ".mp4", ".mpeg", ".mpg", ".mov", ".avi", ".mkv", ".wmv",
        ".m4v", ".3gp", ".webm", ".mts"
    ]

    @property
    def all_extensions(self) -> list[str]:
        return self.image_extensions + self.video_extensions

    class Config:
        env_file = str(Path(__file__).parent.parent.parent / ".env")
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
