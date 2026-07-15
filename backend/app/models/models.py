import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, Text,
    ForeignKey, Table, JSON, LargeBinary, Index
)
from sqlalchemy.orm import relationship

from app.core.database import Base

# Tabela associativa entre Media e Person (rostos detectados)
media_faces = Table(
    "media_faces",
    Base.metadata,
    Column("media_id", Integer, ForeignKey("media.id"), primary_key=True),
    Column("face_id", Integer, ForeignKey("faces.id"), primary_key=True),
)

# Tabela associativa entre Media e Tag
media_tags = Table(
    "media_tags",
    Base.metadata,
    Column("media_id", Integer, ForeignKey("media.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)

# Tabela associativa entre Album e Media
album_media = Table(
    "album_media",
    Base.metadata,
    Column("album_id", Integer, ForeignKey("albums.id"), primary_key=True),
    Column("media_id", Integer, ForeignKey("media.id"), primary_key=True),
)


class Media(Base):
    """Representa uma foto ou vídeo no sistema."""
    __tablename__ = "media"

    # Índice composto que cobre o filtro + ordenação do manifesto de sync
    # (is_duplicate == False, is_organized == True, order by updated_at asc, id asc),
    # evitando full scan e acelerando as páginas altas do sync do app.
    __table_args__ = (
        Index("ix_media_sync_manifest", "is_duplicate", "is_organized", "updated_at", "id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # Caminho original e organizado
    original_path = Column(String, nullable=False)
    organized_path = Column(String, nullable=True, index=True)
    filename = Column(String, nullable=False, index=True)

    # Tipo de mídia
    media_type = Column(String, nullable=False)  # "image" ou "video"
    mime_type = Column(String, nullable=True)

    # Hashes para detecção de duplicatas
    sha256_hash = Column(String(64), nullable=True, index=True)
    perceptual_hash = Column(String(64), nullable=True, index=True)

    # Metadados EXIF
    date_taken = Column(DateTime, nullable=True, index=True)
    date_file = Column(DateTime, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)  # Para vídeos
    video_codec = Column(String, nullable=True)  # Codec do vídeo (h264, mpeg4, wmv3, etc.)
    needs_transcode = Column(Boolean, default=False)  # True se codec incompatível com browser
    camera_make = Column(String, nullable=True)
    camera_model = Column(String, nullable=True)

    # Geolocalização (EXIF GPS)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)

    # Descrição IA (Azure OpenAI Vision)
    ai_description = Column(Text, nullable=True)
    ai_location = Column(String, nullable=True)
    ai_scene_type = Column(String, nullable=True)
    ai_objects = Column(JSON, nullable=True)  # Lista de objetos detectados
    ai_processed = Column(Boolean, default=False, index=True)
    ai_processed_at = Column(DateTime, nullable=True)
    faces_processed = Column(Boolean, default=False, index=True)

    # Status de processamento
    is_organized = Column(Boolean, default=False, index=True)
    is_duplicate = Column(Boolean, default=False, index=True)
    duplicate_of_id = Column(Integer, ForeignKey("media.id"), nullable=True)
    missing_since = Column(DateTime, nullable=True)  # Quando o arquivo sumiu do disco

    # Timestamps
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relacionamentos
    faces = relationship("Face", secondary=media_faces, back_populates="media_items")
    tags = relationship("Tag", secondary=media_tags, back_populates="media_items")
    albums = relationship("Album", secondary=album_media, back_populates="media_items")
    duplicate_of = relationship("Media", remote_side=[id])


class Person(Base):
    """Representa uma pessoa identificada no sistema."""
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    is_confirmed = Column(Boolean, default=False)
    avatar_face_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relacionamentos
    faces = relationship("Face", back_populates="person")


class Face(Base):
    """Representa um rosto detectado em uma mídia."""
    __tablename__ = "faces"

    id = Column(Integer, primary_key=True, index=True)

    # Hash do conteúdo da mídia onde o rosto foi detectado (para re-link automático)
    media_sha256 = Column(String(64), nullable=True, index=True)

    # Posição do rosto na imagem (bounding box)
    bbox_x = Column(Integer, nullable=True)
    bbox_y = Column(Integer, nullable=True)
    bbox_width = Column(Integer, nullable=True)
    bbox_height = Column(Integer, nullable=True)

    # Encoding do rosto (512-dimensional ArcFace embedding)
    encoding = Column(LargeBinary, nullable=True)

    # Pessoa associada
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=True, index=True)
    confidence = Column(Float, nullable=True)
    is_confirmed = Column(Boolean, default=False)
    is_ignored = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relacionamentos
    person = relationship("Person", back_populates="faces")
    media_items = relationship("Media", secondary=media_faces, back_populates="faces")


class Tag(Base):
    """Tags/etiquetas para classificar mídias."""
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    category = Column(String, nullable=True)  # "location", "event", "object", etc.
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relacionamentos
    media_items = relationship("Media", secondary=media_tags, back_populates="tags")


class Album(Base):
    """Álbum criado pelo usuário para agrupar mídias."""
    __tablename__ = "albums"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    cover_media_id = Column(Integer, ForeignKey("media.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relacionamentos
    media_items = relationship("Media", secondary=album_media, back_populates="albums")
    cover_media = relationship("Media", foreign_keys=[cover_media_id])


class ProcessingJob(Base):
    """Rastreia jobs de processamento em background."""
    __tablename__ = "processing_jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_type = Column(String, nullable=False)  # "scan", "organize", "ai_process", "face_detect"
    status = Column(String, default="pending")  # "pending", "running", "completed", "failed"
    total_items = Column(Integer, default=0)
    processed_items = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class AiCache(Base):
    """Cache de descrições IA por hash do conteúdo. Sobrevive a reset de Media."""
    __tablename__ = "ai_cache"

    id = Column(Integer, primary_key=True, index=True)
    sha256_hash = Column(String(64), nullable=False, unique=True, index=True)
    ai_description = Column(Text, nullable=True)
    ai_location = Column(String, nullable=True)
    ai_scene_type = Column(String, nullable=True)
    ai_objects = Column(JSON, nullable=True)
    processed_at = Column(DateTime, default=datetime.datetime.utcnow)


class User(Base):
    """Usuário do sistema com autenticação."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
