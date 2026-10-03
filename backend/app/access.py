"""Quem pode fazer o quê.

- dono: criou o artigo; lê, edita, convida e remove pessoas, escolhe a organização.
- coautor: aceitou um convite para o artigo; lê e edita.
- organização: é membro da organização do artigo; lê e edita.
"""
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Article, ArticleMember, Organization, OrgMember, User


def article_role(db: Session, article: Article, user: User) -> str | None:
    if article.owner_id == user.id:
        return "dono"
    if db.get(ArticleMember, (article.id, user.id)):
        return "coautor"
    if article.org_id and db.get(OrgMember, (article.org_id, user.id)):
        return "organizacao"
    return None


def visible_articles(user: User):
    """Consulta com todos os artigos que a pessoa pode abrir."""
    member_of = select(ArticleMember.article_id).where(ArticleMember.user_id == user.id)
    orgs = select(OrgMember.org_id).where(OrgMember.user_id == user.id)
    return select(Article).where(or_(
        Article.owner_id == user.id, Article.id.in_(member_of), Article.org_id.in_(orgs),
    ))


def get_article(db: Session, article_id: int, user: User, owner_only: bool = False) -> Article:
    article = db.get(Article, article_id)
    role = article_role(db, article, user) if article else None
    # 404 também para artigo alheio: não revela que ele existe.
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artigo não encontrado.")
    if owner_only and role != "dono":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Só quem criou o artigo pode fazer isso.")
    article.role = role
    return article


def org_member(db: Session, org: Organization, user: User) -> bool:
    return org.owner_id == user.id or db.get(OrgMember, (org.id, user.id)) is not None


def get_org(db: Session, org_id: int, user: User, owner_only: bool = False) -> Organization:
    org = db.get(Organization, org_id)
    if org is None or not org_member(db, org, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organização não encontrada.")
    if owner_only and org.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Só quem criou a organização pode fazer isso.")
    return org
