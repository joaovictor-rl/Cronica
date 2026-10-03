"""Artigos: criar (de um modelo ou do Overleaf), listar, organização e coautores."""
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import func, select

from app import access, invites, versioning
from app.access import get_article
from app.document.service import title_of
from app.document.templates import BY_ID as TEMPLATES
from app.ingest import decode_text
from app.models import Article, ArticleMember, Invite, Organization, User, Version
from app.routers.versions import read_zip, save_version
from app.schemas import (
    ArticleCreate,
    ArticleOut,
    ArticleUpdate,
    CodeIn,
    InviteOut,
    MemberOut,
    PeopleOut,
    UserCard,
)
from app.security import DB, CurrentUser

router = APIRouter(prefix="/articles", tags=["artigos"])


def article_out(db, article: Article, role: str, stats=None) -> ArticleOut:
    if stats is None:
        stats = db.execute(select(func.count(Version.hash), func.max(Version.created_at)).where(Version.article_id == article.id)).one()
    org = db.get(Organization, article.org_id) if article.org_id else None
    return ArticleOut(
        id=article.id, title=article.title, created_at=article.created_at, head=article.head_hash,
        versions=stats[0], updated_at=stats[1], role=role, org_id=article.org_id, org_name=org.name if org else None,
    )


def check_org(db, org_id: int | None, user: User) -> None:
    if org_id is not None:
        access.get_org(db, org_id, user)


@router.post("", response_model=ArticleOut, status_code=status.HTTP_201_CREATED)
def create_article(data: ArticleCreate, db: DB, user: CurrentUser):
    check_org(db, data.org_id, user)
    if data.template and data.template not in TEMPLATES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Esse modelo de artigo não existe.")
    article = versioning.create_article(db, data.title, user)
    article.org_id = data.org_id
    db.commit()
    if data.template:
        chosen = TEMPLATES[data.template]
        save_version(db, article, chosen.build(data.title, user.name), f"Artigo criado a partir do modelo {chosen.name}", None, user)
    return article_out(db, article, "dono")


@router.post("/import", response_model=ArticleOut, status_code=status.HTTP_201_CREATED)
async def import_article(db: DB, user: CurrentUser, file: UploadFile = File(..., description="Zip exportado do Overleaf")):
    files = await read_zip(file)
    main = next((p for p in files if p.endswith(".tex") and b"\\documentclass" in files[p]), None)
    title = (title_of(decode_text(files[main])) if main else None) or (file.filename or "Artigo importado").rsplit(".", 1)[0]
    article = versioning.create_article(db, title[:300], user)
    save_version(db, article, files, "Importado do Overleaf", None, user)
    return article_out(db, article, "dono")


@router.get("", response_model=list[ArticleOut])
def list_articles(db: DB, user: CurrentUser):
    articles = db.scalars(access.visible_articles(user)).all()
    stats = {row[0]: row[1:] for row in db.execute(
        select(Version.article_id, func.count(Version.hash), func.max(Version.created_at))
        .where(Version.article_id.in_([a.id for a in articles])).group_by(Version.article_id)
    )}
    out = [article_out(db, a, access.article_role(db, a, user), stats.get(a.id, (0, None))) for a in articles]
    return sorted(out, key=lambda a: a.updated_at or a.created_at, reverse=True)


@router.get("/{article_id}", response_model=ArticleOut)
def read_article(article_id: int, db: DB, user: CurrentUser):
    article = get_article(db, article_id, user)
    return article_out(db, article, article.role)


@router.patch("/{article_id}", response_model=ArticleOut)
def update_article(article_id: int, data: ArticleUpdate, db: DB, user: CurrentUser):
    """Muda a organização do artigo (null tira de qualquer organização)."""
    article = get_article(db, article_id, user, owner_only=True)
    if "org_id" in data.model_fields_set:
        check_org(db, data.org_id, user)
        article.org_id = data.org_id
        db.commit()
    return article_out(db, article, "dono")


# ---------- coautores ----------

@router.get("/{article_id}/members", response_model=PeopleOut)
def list_members(article_id: int, db: DB, user: CurrentUser):
    article = get_article(db, article_id, user)
    members = [MemberOut(user=UserCard.model_validate(db.get(User, article.owner_id)), role="dono")]
    for m in db.scalars(select(ArticleMember).where(ArticleMember.article_id == article.id).order_by(ArticleMember.added_at)):
        members.append(MemberOut(user=UserCard.model_validate(m.user), role="coautor"))
    pending = [invites.invite_out(db, i) for i in invites.pending(db, "artigo", article.id)] if article.role == "dono" else []
    return PeopleOut(members=members, pending=pending)


@router.post("/{article_id}/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def invite_coauthor(article_id: int, data: CodeIn, db: DB, user: CurrentUser):
    article = get_article(db, article_id, user, owner_only=True)
    return invites.send(db, "artigo", article.id, user, data.code)


@router.delete("/{article_id}/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_invite(article_id: int, invite_id: int, db: DB, user: CurrentUser):
    article = get_article(db, article_id, user, owner_only=True)
    invites.cancel(db, db.get(Invite, invite_id), "artigo", article.id)


@router.delete("/{article_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(article_id: int, user_id: int, db: DB, user: CurrentUser):
    """O dono tira um coautor, ou o coautor sai sozinho. As versões que ele salvou continuam no histórico."""
    article = get_article(db, article_id, user)
    if user_id != user.id and article.role != "dono":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Só quem criou o artigo pode tirar outras pessoas.")
    if user_id == article.owner_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Quem criou o artigo não pode sair dele.")
    member = db.get(ArticleMember, (article.id, user_id))
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Essa pessoa não é coautora deste artigo.")
    db.delete(member)
    db.commit()
