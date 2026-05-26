from pydantic_settings import BaseSettings
from pydantic import field_validator
from pathlib import Path


class Settings(BaseSettings):
    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_key: str = ""
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_api_version: str = "2024-08-01-preview"

    # Diretórios
    source_dir: str = "/home/kkirner/src/pics/FOTOS/source"
    organized_dir: str = "/home/kkirner/src/pics/FOTOS/organized"
    trash_dir: str = "/home/kkirner/src/pics/FOTOS/trash"

    # Organização
    # Padrão: "year/month" = YYYY/MM/  |  "year_month" = YYYY_MM[_descricao]/
    organization_pattern: str = "year/month"
    # Pastas de biblioteca adicionais (além de organized_dir) - separadas por vírgula no .env
    library_folders: list[str] = []

    @field_validator("library_folders", mode="before")
    @classmethod
    def parse_library_folders(cls, v):
        if isinstance(v, str):
            return [f.strip() for f in v.split(",") if f.strip()]
        return v

    # Banco de dados
    database_url: str = "sqlite:///./pics.db"

    # Servidor
    host: str = "0.0.0.0"
    port: int = 8000

    # Processamento
    batch_size: int = 10
    max_concurrent_ai_calls: int = 3
    scan_interval_minutes: int = 30

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
