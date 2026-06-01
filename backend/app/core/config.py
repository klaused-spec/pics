from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
from pathlib import Path
from typing import Any


class Settings(BaseSettings):
    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_key: str = ""
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_api_version: str = "2024-08-01-preview"

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

    # Banco de dados
    database_url: str = "sqlite:///./pics.db"

    # Servidor
    host: str = "0.0.0.0"
    port: int = 8000

    # Processamento
    batch_size: int = 10
    max_concurrent_ai_calls: int = 3
    scan_interval_minutes: int = 30
    scan_workers: int = 4  # Número de threads paralelas para scan (SHA256, metadados, pHash)

    # Extensões suportadas
    image_extensions: list[str] = [
        ".jpg", ".jpeg", ".png", ".heic", ".heif",
        ".webp", ".tiff", ".tif", ".bmp", ".gif"
    ]
    video_extensions: list[str] = [
        ".mp4", ".mpeg", ".mpg", ".mov", ".avi", ".mkv", ".wmv",
        ".m4v", ".3gp", ".webm"
    ]

    @property
    def all_extensions(self) -> list[str]:
        return self.image_extensions + self.video_extensions

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
