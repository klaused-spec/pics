"""
Schemas Pydantic para validação de dados.
"""
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


# ===== AUTH =====
class UserLogin(BaseModel):
    """Schema para login de usuário."""
    email: str
    password: str


class UserRegister(BaseModel):
    """Schema para registro de novo usuário."""
    email: str
    password: str


class UserResponse(BaseModel):
    """Schema para resposta de usuário."""
    id: int
    email: str
    created_at: datetime

    class Config:
        from_attributes = True


class UserAdminResponse(BaseModel):
    """Schema para resposta de usuário na área administrativa."""
    id: int
    email: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    """Schema para criação de usuário pela área administrativa."""
    email: str
    password: str


class PasswordUpdate(BaseModel):
    """Schema para alterar a senha de um usuário."""
    password: str


class TokenResponse(BaseModel):
    """Schema para resposta de token."""
    access_token: str
    token_type: str
    user: UserResponse


# ===== MEDIA =====
class MediaResponse(BaseModel):
    """Schema para resposta de mídia."""
    id: int
    filename: str
    media_type: str
    created_at: datetime

    class Config:
        from_attributes = True


# ===== PERSON =====
class PersonResponse(BaseModel):
    """Schema para resposta de pessoa."""
    id: int
    name: str
    created_at: datetime

    class Config:
        from_attributes = True


# ===== ALBUM =====
class AlbumResponse(BaseModel):
    """Schema para resposta de álbum."""
    id: int
    name: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
