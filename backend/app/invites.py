"""Convites por código pessoal, para artigos e organizações."""
import re
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, ArticleMember, Invite, Organization, OrgMember, User
from app.schemas import InviteOut, UserCard


def normalize_code(code: str) -> str:
    raw = re.sub(r"[^0-9A-Za-z]", "", code).upper()
    return f"{raw[:4]}-{raw[4:]}" if len(raw) == 8 else raw


def user_by_code(db: Session, code: str, viewer: User) -> User:
    # Contas da demonstração só se encontram entre si, e contas reais nunca encontram as da demonstração.
    user = db.scalar(select(User).where(
        User.code == normalize_code(code), User.sandbox.is_not_distinct_from(viewer.sandbox),
    ))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nenhuma pessoa tem esse código. Confira com quem passou.")
    return user


def target_name(db: Session, invite: Invite) -> str:
    target = db.get(Article if invite.kind == "artigo" else Organization, invite.target_id)
    return (target.title if invite.kind == "artigo" else target.name) if target else "(removido)"


def invite_out(db: Session, invite: Invite) -> InviteOut:
    return InviteOut(
        id=invite.id, kind=invite.kind, target_id=invite.target_id, target_name=target_name(db, invite),
        sender=UserCard.model_validate(invite.sender), receiver=UserCard.model_validate(invite.receiver),
        created_at=invite.created_at,
    )


def is_member(db: Session, kind: str, target_id: int, user_id: int) -> bool:
    if kind == "artigo":
        article = db.get(Article, target_id)
        return article.owner_id == user_id or db.get(ArticleMember, (target_id, user_id)) is not None
    org = db.get(Organization, target_id)
    return org.owner_id == user_id or db.get(OrgMember, (target_id, user_id)) is not None


def pending(db: Session, kind: str, target_id: int) -> list[Invite]:
    return list(db.scalars(select(Invite).where(
        Invite.kind == kind, Invite.target_id == target_id, Invite.status == "pendente",
    ).order_by(Invite.created_at)))


def send(db: Session, kind: str, target_id: int, sender: User, code: str) -> InviteOut:
    receiver = user_by_code(db, code, sender)
    if receiver.id == sender.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Esse é o seu próprio código.")
    if is_member(db, kind, target_id, receiver.id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{receiver.name} já participa.")
    if any(i.to_id == receiver.id for i in pending(db, kind, target_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{receiver.name} já tem um convite esperando resposta.")
    invite = Invite(kind=kind, target_id=target_id, from_id=sender.id, to_id=receiver.id)
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite_out(db, invite)


def answer(db: Session, invite: Invite, accept: bool) -> None:
    if is_member(db, invite.kind, invite.target_id, invite.to_id):
        accept = False  # já entrou por outro caminho; só fecha o convite
    elif accept and invite.kind == "artigo":
        db.add(ArticleMember(article_id=invite.target_id, user_id=invite.to_id))
    elif accept:
        db.add(OrgMember(org_id=invite.target_id, user_id=invite.to_id))
    invite.status = "aceito" if accept else "recusado"
    invite.answered_at = datetime.now(timezone.utc)
    db.commit()


def drop_target(db: Session, kind: str, target_id: int) -> None:
    for invite in pending(db, kind, target_id):
        db.delete(invite)


def cancel(db: Session, invite: Invite | None, kind: str, target_id: int) -> None:
    if invite is None or invite.kind != kind or invite.target_id != target_id or invite.status != "pendente":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Convite não encontrado.")
    db.delete(invite)
    db.commit()
