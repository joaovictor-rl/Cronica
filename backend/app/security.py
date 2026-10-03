import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import JWT_EXPIRES_MINUTES, JWT_SECRET
from app.database import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRES_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expires}, JWT_SECRET, algorithm="HS256")


def expired(moment: datetime | None) -> bool:
    if moment is None:
        return False
    if moment.tzinfo is None:  # o SQLite devolve datas sem fuso; elas são gravadas em UTC
        moment = moment.replace(tzinfo=timezone.utc)
    return moment < datetime.now(timezone.utc)


def current_user(token: Annotated[str, Depends(oauth2_scheme)], db: Annotated[Session, Depends(get_db)]) -> User:
    try:
        user = db.get(User, int(jwt.decode(token, JWT_SECRET, algorithms=["HS256"])["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        user = None
    if user is None or user.is_closed or expired(user.expires_at):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão inválida ou expirada. Faça login de novo.",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


# Atalhos para as rotas: `db: DB` abre o banco e `user: CurrentUser` exige login.
DB = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(current_user)]


# Limite de tentativas por endereço IP, contra quem tenta adivinhar senhas ou criar contas em massa.
# Fica na memória do servidor: simples, e suficiente para um site com um servidor só.
attempts: dict[str, deque] = defaultdict(deque)


def rate_limit(times: int, seconds: int):
    def check(request: Request):
        key = f"{request.url.path}:{request.client.host if request.client else '?'}"
        now, recent = time.monotonic(), attempts[key]
        while recent and now - recent[0] > seconds:
            recent.popleft()
        if len(recent) >= times:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Muitas tentativas seguidas. Espere um minuto e tente de novo.")
        recent.append(now)
    return Depends(check)
