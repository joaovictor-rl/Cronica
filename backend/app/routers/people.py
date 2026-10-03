"""Pessoas: achar alguém pelo código, ver o perfil de quem escreve com você, fotos e convites recebidos."""
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app import invites, pictures
from app.access import visible_articles
from app.models import Article, Invite, Organization, OrgMember, User
from app.schemas import InviteOut, PublicProfile, UserCard
from app.security import DB, CurrentUser

router = APIRouter(tags=["pessoas"])


def picture_response(content: bytes | None) -> Response:
    if content is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sem foto.")
    # A interface pede a foto com ?v=<data da foto>, então dá para guardar em cache sem medo.
    return Response(content, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.get("/users/by-code/{code}", response_model=UserCard)
def find_by_code(code: str, db: DB, user: CurrentUser):
    """Mostra de quem é um código antes de convidar, para não chamar a pessoa errada."""
    return invites.user_by_code(db, code, user)


@router.get("/users/{user_id}", response_model=PublicProfile)
def public_profile(user_id: int, db: DB, user: CurrentUser):
    """Perfil de outra pessoa: só para quem escreve com ela, está na mesma organização ou trocou convites."""
    other = db.get(User, user_id)
    if other is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Perfil não encontrado.")
    mine = set(db.scalars(visible_articles(user).with_only_columns(Article.id)))
    theirs = set(db.scalars(visible_articles(other).with_only_columns(Article.id)))
    shared = mine & theirs
    my_orgs = select(OrgMember.org_id).where(OrgMember.user_id == user.id)
    orgs = db.scalars(select(Organization).join(OrgMember, OrgMember.org_id == Organization.id)
                      .where(OrgMember.user_id == other.id, Organization.id.in_(my_orgs))).all()
    invited = db.scalar(select(Invite.id).where(Invite.status == "pendente", or_(
        and_(Invite.from_id == user.id, Invite.to_id == other.id),
        and_(Invite.from_id == other.id, Invite.to_id == user.id),
    )).limit(1))
    if other.id != user.id and not shared and not orgs and invited is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Perfil não encontrado.")
    articles = db.scalars(select(Article).where(Article.id.in_(shared)).order_by(Article.title)).all() if shared else []
    return PublicProfile.model_validate(other).model_copy(update={
        "shared_articles": [{"id": a.id, "title": a.title} for a in articles],
        "shared_orgs": [{"id": o.id, "name": o.name, "picture_at": o.picture_at} for o in orgs],
    })


@router.get("/users/{user_id}/picture")
def user_picture(user_id: int, db: DB, user: CurrentUser):
    found = db.get(User, user_id)
    return picture_response(found.picture if found else None)


@router.post("/auth/me/picture", response_model=UserCard)
async def upload_my_picture(db: DB, user: CurrentUser, file: UploadFile = File(...)):
    user.picture = await pictures.read_upload(file)
    user.picture_at = datetime.now(timezone.utc)
    db.commit()
    return user


@router.delete("/auth/me/picture", response_model=UserCard)
def delete_my_picture(db: DB, user: CurrentUser):
    user.picture = None
    user.picture_at = None
    db.commit()
    return user


@router.get("/invites", response_model=list[InviteOut])
def my_invites(db: DB, user: CurrentUser):
    """Convites que estão esperando a sua resposta."""
    found = db.scalars(select(Invite).where(Invite.to_id == user.id, Invite.status == "pendente").order_by(Invite.created_at.desc()))
    return [invites.invite_out(db, i) for i in found]


def my_invite(db: Session, invite_id: int, user: User) -> Invite:
    invite = db.get(Invite, invite_id)
    if invite is None or invite.to_id != user.id or invite.status != "pendente":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Convite não encontrado.")
    if db.get(Article if invite.kind == "artigo" else Organization, invite.target_id) is None:
        db.delete(invite)
        db.commit()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esse convite era para algo que não existe mais.")
    return invite


@router.post("/invites/{invite_id}/accept", status_code=status.HTTP_204_NO_CONTENT)
def accept_invite(invite_id: int, db: DB, user: CurrentUser):
    invites.answer(db, my_invite(db, invite_id, user), accept=True)


@router.post("/invites/{invite_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline_invite(invite_id: int, db: DB, user: CurrentUser):
    invites.answer(db, my_invite(db, invite_id, user), accept=False)
