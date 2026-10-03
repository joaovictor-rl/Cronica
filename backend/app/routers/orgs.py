"""Organizações: um grupo de pesquisa, uma turma, um laboratório.

Quem é membro lê e edita todos os artigos que estão na organização.
Só quem criou a organização convida, tira pessoas e muda nome, descrição e foto.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import access, invites, pictures
from app.models import Article, Invite, Organization, OrgMember, User
from app.routers.articles import article_out
from app.routers.people import picture_response
from app.schemas import (
    ArticleOut,
    CodeIn,
    InviteOut,
    MemberOut,
    OrgCreate,
    OrgOut,
    OrgUpdate,
    PeopleOut,
    UserCard,
)
from app.security import DB, CurrentUser

router = APIRouter(prefix="/orgs", tags=["organizações"])


def org_out(db: Session, org: Organization, user: User) -> OrgOut:
    members = db.scalar(select(func.count()).select_from(OrgMember).where(OrgMember.org_id == org.id))
    articles = db.scalar(select(func.count()).select_from(Article).where(Article.org_id == org.id))
    return OrgOut(
        id=org.id, name=org.name, description=org.description, owner=UserCard.model_validate(db.get(User, org.owner_id)),
        created_at=org.created_at, picture_at=org.picture_at, members=members, articles=articles,
        is_owner=org.owner_id == user.id,
    )


@router.post("", response_model=OrgOut, status_code=status.HTTP_201_CREATED)
def create_org(data: OrgCreate, db: DB, user: CurrentUser):
    org = Organization(name=data.name.strip(), description=data.description.strip(), owner_id=user.id)
    db.add(org)
    db.flush()
    db.add(OrgMember(org_id=org.id, user_id=user.id))  # o dono também aparece entre os membros
    db.commit()
    return org_out(db, org, user)


@router.get("", response_model=list[OrgOut])
def list_orgs(db: DB, user: CurrentUser):
    found = db.scalars(
        select(Organization).join(OrgMember, OrgMember.org_id == Organization.id)
        .where(OrgMember.user_id == user.id).order_by(Organization.name)
    )
    return [org_out(db, org, user) for org in found]


@router.get("/{org_id}", response_model=OrgOut)
def read_org(org_id: int, db: DB, user: CurrentUser):
    return org_out(db, access.get_org(db, org_id, user), user)


@router.patch("/{org_id}", response_model=OrgOut)
def update_org(org_id: int, data: OrgUpdate, db: DB, user: CurrentUser):
    org = access.get_org(db, org_id, user, owner_only=True)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(org, field, value.strip())
    db.commit()
    return org_out(db, org, user)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_org(org_id: int, db: DB, user: CurrentUser):
    """Apaga a organização. Os artigos não somem: voltam a ser só de quem os criou e dos coautores."""
    org = access.get_org(db, org_id, user, owner_only=True)
    db.execute(update(Article).where(Article.org_id == org.id).values(org_id=None))
    for member in db.scalars(select(OrgMember).where(OrgMember.org_id == org.id)):
        db.delete(member)
    invites.drop_target(db, "organizacao", org.id)
    db.flush()
    db.delete(org)
    db.commit()


@router.get("/{org_id}/members", response_model=PeopleOut)
def list_members(org_id: int, db: DB, user: CurrentUser):
    org = access.get_org(db, org_id, user)
    found = db.scalars(select(OrgMember).where(OrgMember.org_id == org.id).order_by(OrgMember.joined_at))
    members = [
        MemberOut(user=UserCard.model_validate(m.user), role="dono" if m.user_id == org.owner_id else "membro")
        for m in found
    ]
    pending = [invites.invite_out(db, i) for i in invites.pending(db, "organizacao", org.id)] if org.owner_id == user.id else []
    return PeopleOut(members=members, pending=pending)


@router.get("/{org_id}/articles", response_model=list[ArticleOut])
def list_articles(org_id: int, db: DB, user: CurrentUser):
    org = access.get_org(db, org_id, user)
    found = db.scalars(select(Article).where(Article.org_id == org.id))
    out = [article_out(db, a, access.article_role(db, a, user)) for a in found]
    return sorted(out, key=lambda a: a.updated_at or a.created_at, reverse=True)


@router.post("/{org_id}/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def invite_member(org_id: int, data: CodeIn, db: DB, user: CurrentUser):
    org = access.get_org(db, org_id, user, owner_only=True)
    return invites.send(db, "organizacao", org.id, user, data.code)


@router.delete("/{org_id}/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_invite(org_id: int, invite_id: int, db: DB, user: CurrentUser):
    org = access.get_org(db, org_id, user, owner_only=True)
    invites.cancel(db, db.get(Invite, invite_id), "organizacao", org.id)


@router.delete("/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(org_id: int, user_id: int, db: DB, user: CurrentUser):
    org = access.get_org(db, org_id, user)
    if user_id != user.id and org.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Só quem criou a organização pode tirar outras pessoas.")
    if user_id == org.owner_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Quem criou a organização não pode sair dela.")
    member = db.get(OrgMember, (org.id, user_id))
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Essa pessoa não é membro da organização.")
    db.delete(member)
    db.commit()


@router.get("/{org_id}/picture")
def org_picture(org_id: int, db: DB, user: CurrentUser):
    return picture_response(access.get_org(db, org_id, user).picture)


@router.post("/{org_id}/picture", response_model=OrgOut)
async def upload_org_picture(org_id: int, db: DB, user: CurrentUser, file: UploadFile = File(...)):
    org = access.get_org(db, org_id, user, owner_only=True)
    org.picture = await pictures.read_upload(file)
    org.picture_at = datetime.now(timezone.utc)
    db.commit()
    return org_out(db, org, user)
