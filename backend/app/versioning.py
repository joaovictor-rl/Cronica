import hashlib

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.ingest import looks_like_text
from app.models import Article, Blob, Tree, TreeEntry, User, Version, now


class CommitConflict(Exception):
    def __init__(self, current_head: str | None):
        self.current_head = current_head


class NothingChanged(Exception):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def insert_ignore(db: Session, model):
    # PostgreSQL e SQLite têm "ON CONFLICT DO NOTHING", mas cada um pelo seu dialeto.
    dialect = postgresql if db.get_bind().dialect.name == "postgresql" else sqlite
    return dialect.insert(model).on_conflict_do_nothing()


def tree_hash_of(entries: dict[str, str]) -> str:
    listing = "".join(f"{path}\0{blob}\n" for path, blob in sorted(entries.items()))
    return sha256(listing.encode())


def store_tree(db: Session, files: dict[str, bytes]) -> str:
    entries = {path: sha256(content) for path, content in files.items()}

    # ON CONFLICT DO NOTHING: blobs iguais (de qualquer artigo) são guardados uma vez só.
    blob_rows = [
        {"hash": entries[path], "content": content, "size": len(content), "is_text": looks_like_text(path, content)}
        for path, content in files.items()
    ]
    db.execute(insert_ignore(db, Blob), blob_rows)

    tree_hash = tree_hash_of(entries)
    created = db.scalar(insert_ignore(db, Tree).values(hash=tree_hash).returning(Tree.hash))
    if created:
        db.execute(TreeEntry.__table__.insert(), [
            {"tree_hash": tree_hash, "path": path, "blob_hash": blob} for path, blob in entries.items()
        ])
    return tree_hash


def create_article(db: Session, title: str, owner: User) -> Article:
    article = Article(title=title, owner_id=owner.id)
    db.add(article)
    db.commit()
    return article


def commit(db: Session, article: Article, files: dict[str, bytes], message: str, base: str | None,
           author: User, created_at=None) -> Version:
    """Cria uma versão nova. `base` é a versão que a pessoa tinha aberta: se outra pessoa salvou antes, é conflito."""
    # Trava a linha do artigo: dois salvamentos na mesma base não passam ao mesmo tempo.
    # populate_existing relê a versão atual depois da trava, em vez de usar a cópia que já estava na memória.
    article = db.scalar(select(Article).where(Article.id == article.id).with_for_update().execution_options(populate_existing=True))
    if article.head_hash != base:
        raise CommitConflict(article.head_hash)

    tree_hash = store_tree(db, files)
    if article.head_hash and db.get(Version, article.head_hash).tree_hash == tree_hash:
        raise NothingChanged()

    created_at = created_at or now()
    header = f"tree {tree_hash}\nparent {article.head_hash or ''}\nauthor {author.id}\ndate {created_at.isoformat()}\n\n{message}"
    version = Version(
        hash=sha256(header.encode()), article_id=article.id, parent_hash=article.head_hash,
        tree_hash=tree_hash, author_id=author.id, message=message, created_at=created_at,
    )
    db.add(version)
    db.flush()
    article.head_hash = version.hash
    db.commit()
    return version


def history(db: Session, start: str | None, limit: int = 100) -> list[Version]:
    versions = []
    current = start
    while current and len(versions) < limit:
        version = db.get(Version, current)
        versions.append(version)
        current = version.parent_hash
    return versions


def entries_of(db: Session, tree_hash: str) -> dict[str, str]:
    rows = db.execute(select(TreeEntry.path, TreeEntry.blob_hash).where(TreeEntry.tree_hash == tree_hash))
    return dict(rows.all())


def blob_at(db: Session, tree_hash: str, path: str) -> Blob | None:
    entry = db.get(TreeEntry, (tree_hash, path))
    return entry.blob if entry else None
