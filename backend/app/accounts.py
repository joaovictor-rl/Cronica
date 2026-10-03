"""Apagar contas (a pedido da pessoa ou quando uma demonstração acaba) e exportar os dados de alguém."""
import io
import json
import zipfile

from sqlalchemy import delete, or_, select, update

from app import versioning
from app.models import Article, ArticleMember, Blob, Invite, Organization, OrgMember, Tree, TreeEntry, User, Version, new_code


def delete_users(db, ids: list[int]) -> None:
    """Apaga as contas e tudo o que é delas: artigos que criaram, organizações, convites e participações.

    Quem salvou versões em artigos de outras pessoas não some do histórico desses artigos: a conta
    é anonimizada (sem nome, e-mail, foto nem perfil) em vez de apagada.
    """
    if not ids:
        return
    articles = select(Article.id).where(Article.owner_id.in_(ids)).scalar_subquery()
    orgs = select(Organization.id).where(Organization.owner_id.in_(ids)).scalar_subquery()
    db.execute(delete(Invite).where(or_(
        Invite.from_id.in_(ids), Invite.to_id.in_(ids),
        (Invite.kind == "artigo") & Invite.target_id.in_(articles),
        (Invite.kind == "organizacao") & Invite.target_id.in_(orgs),
    )))
    db.execute(delete(ArticleMember).where(or_(ArticleMember.user_id.in_(ids), ArticleMember.article_id.in_(articles))))
    db.execute(delete(OrgMember).where(or_(OrgMember.user_id.in_(ids), OrgMember.org_id.in_(orgs))))
    db.execute(update(Article).where(Article.org_id.in_(orgs)).values(org_id=None))
    db.execute(update(Version).where(Version.article_id.in_(articles)).values(parent_hash=None))
    db.execute(delete(Version).where(Version.article_id.in_(articles)))
    db.execute(delete(Article).where(Article.owner_id.in_(ids)))
    db.execute(delete(Organization).where(Organization.owner_id.in_(ids)))

    authors = set(db.scalars(select(Version.author_id).where(Version.author_id.in_(ids))))
    for user in db.scalars(select(User).where(User.id.in_(authors))):
        anonymize(user)
    db.execute(delete(User).where(User.id.in_([i for i in ids if i not in authors])))
    db.commit()


def anonymize(user: User) -> None:
    user.name, user.email, user.password_hash = "Conta excluída", f"excluida-{user.id}@cronica.invalid", "!"
    user.institution = user.area = user.city = user.bio = user.status = user.interests = ""
    user.lattes = user.orcid = user.website = ""
    user.picture = user.picture_at = None
    user.code = new_code()


def collect_garbage(db) -> None:
    """Apaga árvores e arquivos que nenhuma versão usa mais. Só roda quando o servidor sobe, sem salvamentos no meio."""
    used_trees = select(Version.tree_hash)
    db.execute(delete(TreeEntry).where(TreeEntry.tree_hash.not_in(used_trees)))
    db.execute(delete(Tree).where(Tree.hash.not_in(used_trees)))
    db.execute(delete(Blob).where(Blob.hash.not_in(select(TreeEntry.blob_hash))))
    db.commit()


PROFILE_FIELDS = ["name", "email", "institution", "area", "city", "bio", "status", "interests", "lattes", "orcid",
                  "website", "theme", "pattern", "code", "created_at"]


def export_zip(db, user: User) -> bytes:
    """Tudo o que o Crônica guarda sobre a pessoa: o perfil, a foto e a versão atual de cada artigo que ela criou."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        profile = {field: getattr(user, field) for field in PROFILE_FIELDS}
        articles = db.scalars(select(Article).where(Article.owner_id == user.id)).all()
        profile["artigos"] = [{"titulo": a.title, "criado_em": a.created_at} for a in articles]
        zf.writestr("perfil.json", json.dumps(profile, ensure_ascii=False, indent=2, default=str))
        if user.picture:
            zf.writestr("foto.jpg", user.picture)
        for article in articles:
            if not article.head_hash:
                continue
            entries = versioning.entries_of(db, db.get(Version, article.head_hash).tree_hash)
            for path, blob in entries.items():
                zf.writestr(f"artigos/{article.id} - {article.title[:60].replace('/', '-')}/{path}", db.get(Blob, blob).content)
    return buffer.getvalue()
