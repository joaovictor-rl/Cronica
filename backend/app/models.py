import secrets
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def now():
    return datetime.now(timezone.utc)


CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # sem 0/O, 1/I/L, que se confundem ao ditar o código
THEMES = ("azul", "rosa", "verde", "lilas", "laranja", "noite")
PATTERNS = ("nenhum", "bolinhas", "listras", "xadrez", "confete")


def new_code() -> str:
    """Código pessoal que a pessoa passa para ser convidada, como 'K7QM-4XPA'."""
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    privacy_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    institution: Mapped[str] = mapped_column(String(200), default="", server_default="")
    area: Mapped[str] = mapped_column(String(200), default="", server_default="")
    city: Mapped[str] = mapped_column(String(120), default="", server_default="")
    bio: Mapped[str] = mapped_column(Text, default="", server_default="")
    theme: Mapped[str] = mapped_column(String(20), default="azul", server_default="azul")
    code: Mapped[str] = mapped_column(String(9), default=new_code, server_default="", index=True)
    picture: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    picture_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Personalização do perfil
    status: Mapped[str] = mapped_column(String(140), default="", server_default="")
    interests: Mapped[str] = mapped_column(Text, default="", server_default="")  # um por linha
    lattes: Mapped[str] = mapped_column(String(300), default="", server_default="")
    orcid: Mapped[str] = mapped_column(String(300), default="", server_default="")
    website: Mapped[str] = mapped_column(String(300), default="", server_default="")
    pattern: Mapped[str] = mapped_column(String(20), default="nenhum", server_default="nenhum")
    # Contas da demonstração: cada visitante ganha as suas, que somem quando expiram ou o servidor reinicia.
    sandbox: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_demo(self) -> bool:
        return self.sandbox is not None

    @property
    def is_closed(self) -> bool:
        """Conta excluída que ficou só como nome anônimo no histórico de artigos de outras pessoas."""
        return self.sandbox is None and self.password_hash == "!"

    @property
    def interest_list(self) -> list[str]:
        return [line for line in self.interests.split("\n") if line]


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    picture: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    picture_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrgMember(Base):
    __tablename__ = "org_members"

    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    user: Mapped["User"] = relationship(lazy="joined")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    head_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # versão atual


class ArticleMember(Base):
    """Coautores: quem foi convidado para escrever o artigo junto com o dono."""
    __tablename__ = "article_members"

    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    user: Mapped["User"] = relationship(lazy="joined")


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # "artigo" ou "organizacao"
    target_id: Mapped[int] = mapped_column(Integer)
    from_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    to_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pendente")  # pendente, aceito, recusado
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sender: Mapped["User"] = relationship(foreign_keys=[from_id], lazy="joined")
    receiver: Mapped["User"] = relationship(foreign_keys=[to_id], lazy="joined")


class Blob(Base):
    __tablename__ = "blobs"

    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    size: Mapped[int] = mapped_column(Integer)
    is_text: Mapped[bool] = mapped_column(Boolean)


class Tree(Base):
    __tablename__ = "trees"

    hash: Mapped[str] = mapped_column(String(64), primary_key=True)


class TreeEntry(Base):
    __tablename__ = "tree_entries"

    tree_hash: Mapped[str] = mapped_column(ForeignKey("trees.hash"), primary_key=True)
    path: Mapped[str] = mapped_column(String(1024), primary_key=True)
    blob_hash: Mapped[str] = mapped_column(ForeignKey("blobs.hash"), index=True)

    blob: Mapped[Blob] = relationship(lazy="joined")


class Version(Base):
    __tablename__ = "versions"

    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    parent_hash: Mapped[str | None] = mapped_column(ForeignKey("versions.hash"))
    tree_hash: Mapped[str] = mapped_column(ForeignKey("trees.hash"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    author: Mapped[User] = relationship(lazy="joined")
