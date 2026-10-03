import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

Theme = Literal["azul", "rosa", "verde", "lilas", "laranja", "noite"]
Pattern = Literal["nenhum", "bolinhas", "listras", "xadrez", "confete"]


def web_address(value: str, host: str | None = None) -> str:
    value = value.strip()
    if not value:
        return ""
    if not re.match(r"https?://", value, re.I):
        value = "https://" + value
    parsed = urlparse(value)
    if not parsed.hostname or "." not in parsed.hostname or " " in value:
        raise ValueError("Esse endereço não parece válido.")
    if host and not (parsed.hostname == host or parsed.hostname.endswith("." + host)):
        raise ValueError(f"O endereço precisa ser do {host}.")
    return value


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    accept_privacy: Literal[True]  # concordou com a política de privacidade


class PasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    institution: str = ""
    area: str = ""
    city: str = ""
    bio: str = ""
    created_at: datetime | None = None
    theme: str = "azul"
    pattern: str = "nenhum"
    code: str = ""
    picture_at: datetime | None = None
    status: str = ""
    interests: list[str] = Field(default=[], validation_alias=AliasChoices("interest_list", "interests"))
    lattes: str = ""
    orcid: str = ""
    website: str = ""
    is_demo: bool = False
    expires_at: datetime | None = None


class PublicProfile(BaseModel):
    """O perfil como coautores e membros das mesmas organizações veem: sem e-mail."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    institution: str = ""
    area: str = ""
    city: str = ""
    bio: str = ""
    status: str = ""
    interests: list[str] = Field(default=[], validation_alias=AliasChoices("interest_list", "interests"))
    lattes: str = ""
    orcid: str = ""
    website: str = ""
    theme: str = "azul"
    pattern: str = "nenhum"
    picture_at: datetime | None = None
    created_at: datetime | None = None
    shared_articles: list[dict] = []
    shared_orgs: list[dict] = []


class UserCard(BaseModel):
    """O que outras pessoas veem de alguém: o suficiente para reconhecer quem é."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    institution: str = ""
    picture_at: datetime | None = None


class CodeIn(BaseModel):
    code: str = Field(min_length=4, max_length=20)


class MemberOut(BaseModel):
    user: UserCard
    role: str


class PeopleOut(BaseModel):
    members: list[MemberOut]
    pending: list["InviteOut"] = []


class InviteOut(BaseModel):
    id: int
    kind: str
    target_id: int
    target_name: str
    sender: UserCard
    receiver: UserCard
    created_at: datetime


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field("", max_length=2000)


class OrgUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)


class OrgOut(BaseModel):
    id: int
    name: str
    description: str
    owner: UserCard
    created_at: datetime
    picture_at: datetime | None
    members: int
    articles: int
    is_owner: bool


class ProfileOut(UserOut):
    articles: int
    versions: int
    last_activity: datetime | None


class ProfileUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    institution: str | None = Field(None, max_length=200)
    area: str | None = Field(None, max_length=200)
    city: str | None = Field(None, max_length=120)
    bio: str | None = Field(None, max_length=1000)
    theme: Theme | None = None
    pattern: Pattern | None = None
    status: str | None = Field(None, max_length=140)
    interests: list[str] | None = Field(None, max_length=10)
    lattes: str | None = Field(None, max_length=300)
    orcid: str | None = Field(None, max_length=300)
    website: str | None = Field(None, max_length=300)

    @field_validator("interests")
    @classmethod
    def clean_interests(cls, value):
        if value is None:
            return None
        out = []
        for item in value:
            item = " ".join(item.split())
            if len(item) > 60:
                raise ValueError("Cada interesse pode ter até 60 caracteres.")
            if item and item.lower() not in {o.lower() for o in out}:
                out.append(item)
        return out

    @field_validator("website")
    @classmethod
    def check_website(cls, value):
        return None if value is None else web_address(value)

    @field_validator("lattes")
    @classmethod
    def check_lattes(cls, value):
        if value is None:
            return None
        if re.fullmatch(r"\s*\d{16}\s*", value):
            return "http://lattes.cnpq.br/" + value.strip()
        return web_address(value, "lattes.cnpq.br")

    @field_validator("orcid")
    @classmethod
    def check_orcid(cls, value):
        if value is None or not value.strip():
            return value and ""
        found = re.search(r"\d{4}-\d{4}-\d{4}-\d{3}[\dXx]", value)
        if not found:
            raise ValueError("O ORCID tem o formato 0000-0000-0000-0000.")
        return "https://orcid.org/" + found.group(0).upper()


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    template: str | None = None  # id de um modelo (veja GET /templates); sem modelo, o artigo nasce vazio
    org_id: int | None = None


class ArticleUpdate(BaseModel):
    org_id: int | None = None


class ReferenceIn(BaseModel):
    key: str = Field("", max_length=100)
    type: str = Field("misc", max_length=30)
    fields: dict[str, str] = Field(default_factory=dict, max_length=40)


class ImageIn(BaseModel):
    path: str = Field(min_length=1, max_length=200)
    data: str = Field(min_length=1, max_length=12_000_000)  # base64


class DraftIn(BaseModel):
    """O que está no editor: o documento (ou o código), as referências se mudaram e as imagens novas."""
    base_version: str = Field(min_length=7, max_length=64)
    document: dict | None = None
    source: str | None = Field(None, max_length=2_000_000)
    references: list[ReferenceIn] | None = Field(None, max_length=2000)
    images: list[ImageIn] = Field(default_factory=list, max_length=10)


class EditIn(DraftIn):
    message: str = Field(min_length=1, max_length=2000)


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    created_at: datetime
    head: str | None = None  # versão atual
    versions: int = 0
    updated_at: datetime | None = None
    role: str = "dono"
    org_id: int | None = None
    org_name: str | None = None


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    hash: str
    parent_hash: str | None
    message: str
    created_at: datetime
    author: UserCard


class FileOut(BaseModel):
    path: str
    blob_hash: str
    size: int
    is_text: bool


class VersionDetail(VersionOut):
    files: list[FileOut]


class DiffOut(BaseModel):
    from_version: str
    to_version: str
    files: list[dict]
