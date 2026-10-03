"""Conta e perfil: cadastro, login, demonstração e edição do próprio perfil."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select

from app import accounts, demo
from app.access import visible_articles
from app.models import User, Version, now
from app.schemas import PasswordIn, ProfileOut, ProfileUpdate, Token, UserCreate, UserOut
from app.security import (
    DB,
    CurrentUser,
    check_password,
    create_token,
    hash_password,
    rate_limit,
)

router = APIRouter(prefix="/auth", tags=["conta"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED, dependencies=[rate_limit(5, 60)])
def register(data: UserCreate, db: DB):
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma conta com esse e-mail.")
    user = User(name=data.name, email=email, password_hash=hash_password(data.password), privacy_accepted_at=now())
    db.add(user)
    db.commit()
    return user


@router.post("/login", response_model=Token, dependencies=[rate_limit(10, 60)])
def login(db: DB, form: OAuth2PasswordRequestForm = Depends()):
    user = db.scalar(select(User).where(User.email == form.username.lower(), User.sandbox.is_(None)))
    if not user or not check_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha incorretos.")
    return Token(access_token=create_token(user.id))


def profile(db, user: User) -> ProfileOut:
    articles = db.scalar(select(func.count()).select_from(visible_articles(user).subquery()))
    versions, last = db.execute(
        select(func.count(Version.hash), func.max(Version.created_at)).where(Version.author_id == user.id)
    ).one()
    return ProfileOut(**UserOut.model_validate(user).model_dump(), articles=articles, versions=versions, last_activity=last)


@router.get("/me", response_model=ProfileOut)
def me(db: DB, user: CurrentUser):
    return profile(db, user)


@router.patch("/me", response_model=ProfileOut)
def update_me(data: ProfileUpdate, db: DB, user: CurrentUser):
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(user, field, "\n".join(value) if field == "interests" else value.strip())
    db.commit()
    return profile(db, user)


@router.get("/me/export")
def export_my_data(db: DB, user: CurrentUser):
    """Baixar meus dados: o perfil, a foto e os artigos que a pessoa criou, num .zip."""
    return Response(accounts.export_zip(db, user), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="meus-dados-cronica.zip"'})


@router.post("/me/delete", status_code=status.HTTP_204_NO_CONTENT, dependencies=[rate_limit(5, 60)])
def delete_my_account(data: PasswordIn, db: DB, user: CurrentUser):
    """Excluir a conta. Pede a senha de novo, para ninguém apagar a conta de outra pessoa num computador aberto."""
    if user.sandbox is None and not check_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Senha incorreta.")
    accounts.delete_users(db, [user.id])


@router.post("/demo", response_model=Token, status_code=status.HTTP_201_CREATED, dependencies=[rate_limit(5, 60)])
def start_demo(db: DB):
    """Cria uma demonstração só para quem pediu. Ela some em algumas horas ou quando o servidor reinicia."""
    try:
        user = demo.create_sandbox(db)
    except demo.DemoFull:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Muitas demonstrações abertas agora. Tente de novo daqui a pouco.") from None
    return Token(access_token=create_token(user.id))


@router.post("/demo/switch", response_model=Token)
def switch_demo_account(db: DB, user: CurrentUser):
    """Troca para a outra conta da mesma demonstração, para testar convites dos dois lados."""
    other = demo.other_account(db, user) if user.sandbox else None
    if other is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Só dá para trocar de conta na demonstração.")
    return Token(access_token=create_token(other.id))
