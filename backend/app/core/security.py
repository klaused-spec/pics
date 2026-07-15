"""
Funções de segurança e autenticação JWT.
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

# Configuração de senha - usando pbkdf2_sha256 que é suportado por padrão
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Configuração JWT - usar SECRET_KEY do settings
SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes


def hash_password(password: str) -> str:
    """Hash de senha com bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha corresponde ao hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Cria um JWT token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> dict:
    """Verifica e decodifica um JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")  # JWT sub é string
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido",
            )
        return {"user_id": int(user_id)}  # Converter para int
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
        )


# Dependency para extrair usuário do token
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Extrai o usuário atual a partir do token JWT."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")  # JWT sub é string
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido",
            )
        return {"user_id": int(user_id)}  # Converter para int
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
        )
