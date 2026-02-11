from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status, Header, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database import get_db
from models import User

# Секретный ключ — в продакшене обязательно сгенерируй длинный случайный
SECRET_KEY = "my-very-long-random-secret-1234567890abcdefghijklmnopqrstuvwxyz"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 день для удобства разработки

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def authenticate_user(db: Session, username: str, password: str):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
        authorization: Optional[str] = Header(default=None, alias="Authorization"),
        request: Request = None,
        db: Session = Depends(get_db)
):
    """
    Обязательная авторизация — кидает 401, если токена нет или он неверный.
    Поддерживает токен в заголовке Authorization или в cookie 'access_token'.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось проверить учётные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = None
    # Сначала — стандартный заголовок Authorization
    if authorization:
        token = authorization.replace("Bearer ", "", 1) if authorization.startswith("Bearer ") else authorization

    # Если заголовка нет — пробуем cookie
    if not token and request:
        cookie_token = request.cookies.get("access_token")
        if cookie_token:
            token = cookie_token

    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception

    return user


async def get_current_user_or_none(
        authorization: Optional[str] = Header(default=None, alias="Authorization"),
        request: Request = None,
        db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Опциональная авторизация — возвращает None, если токена нет или он неверный
    Используется для страниц, где пользователь может быть не авторизован
    Теперь поддерживает чтение токена из заголовка Authorization или из cookie 'access_token'.
    """
    token = None

    # Если есть стандартный заголовок Authorization — используем его
    if authorization:
        token = authorization.replace("Bearer ", "", 1) if authorization.startswith("Bearer ") else authorization

    # Если нет заголовка — пробуем cookie
    if not token and request:
        cookie_token = request.cookies.get("access_token")
        if cookie_token:
            token = cookie_token

    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None

    user = db.query(User).filter(User.username == username).first()
    return user