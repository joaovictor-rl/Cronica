"""Versões de um artigo: histórico, comparação, PDF, arquivos e o salvamento do que foi editado no site."""
import base64
import io
import zipfile
from collections import Counter

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select

from app import pictures, versioning
from app.access import get_article
from app.diff.engine import diff_trees
from app.document.bibtex import TYPES as BIB_TYPES
from app.document.bibtex import chunks as bib_chunks
from app.document.bibtex import clean_entries, write_bib
from app.document.blocks import serialize_document
from app.document.images import page_png, pdf_page_count
from app.document.references import citation_style, entry_label, entry_text, walk_spans
from app.document.service import (
    NoMainFile,
    ensure_bibliography,
    load_version,
    pdf_from_files,
    slug,
)
from app.ingest import MAX_ZIP_BYTES, ZipRejected, decode_text, extract_zip
from app.models import Article, Blob, TreeEntry, User, Version
from app.schemas import DiffOut, DraftIn, EditIn, FileOut, VersionDetail, VersionOut
from app.security import DB, CurrentUser

router = APIRouter(prefix="/articles", tags=["versões"])
PAGE_WIDTH = 1000  # largura das páginas do PDF mostradas no site, em pixels
CACHE_FOREVER = {"Cache-Control": "private, max-age=31536000, immutable"}  # o conteúdo de uma versão nunca muda


def resolve_version(db, article: Article, ref: str) -> Version:
    """Aceita o código completo da versão ou o começo dele (pelo menos 7 caracteres), como no Git."""
    ref = ref.lower()
    if len(ref) < 7:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Código de versão curto demais. Use pelo menos 7 caracteres.")
    matches = db.scalars(select(Version).where(Version.article_id == article.id, Version.hash.startswith(ref)).limit(2)).all()
    if not matches:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Versão {ref} não encontrada neste artigo.")
    if len(matches) > 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Mais de uma versão começa com {ref}. Use mais caracteres do código.")
    return matches[0]


def loaded(db, article: Article, ref: str):
    try:
        return load_version(db, resolve_version(db, article, ref))
    except NoMainFile:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Esta versão não tem um arquivo .tex principal.") from None


def save_version(db, article: Article, files: dict[str, bytes], message: str, base: str | None, user: User) -> Version:
    try:
        return versioning.commit(db, article, files, message.strip(), base, user)
    except versioning.CommitConflict as conflict:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, {
            "message": "Alguém salvou uma versão nova enquanto você trabalhava. Abra a versão atual, refaça suas mudanças e salve de novo.",
            "current_head": conflict.current_head,
        }) from None
    except versioning.NothingChanged:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nada mudou em relação à versão atual.") from None


async def read_zip(file: UploadFile) -> dict[str, bytes]:
    try:
        return extract_zip(await file.read(MAX_ZIP_BYTES + 1))
    except ZipRejected as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None


# ---------- leitura ----------

@router.get("/{article_id}/versions", response_model=list[VersionOut])
def list_versions(article_id: int, db: DB, user: CurrentUser, limit: int = Query(100, ge=1, le=500)):
    return versioning.history(db, get_article(db, article_id, user).head_hash, limit)


@router.get("/{article_id}/versions/{ref}", response_model=VersionDetail)
def read_version(article_id: int, ref: str, db: DB, user: CurrentUser):
    version = resolve_version(db, get_article(db, article_id, user), ref)
    rows = db.execute(
        select(TreeEntry.path, Blob.hash, Blob.size, Blob.is_text).join(Blob, Blob.hash == TreeEntry.blob_hash)
        .where(TreeEntry.tree_hash == version.tree_hash).order_by(TreeEntry.path)
    ).all()
    files = [FileOut(path=r.path, blob_hash=r.hash, size=r.size, is_text=r.is_text) for r in rows]
    return VersionDetail(**VersionOut.model_validate(version).model_dump(), files=files)


@router.get("/{article_id}/versions/{ref}/files/{path:path}")
def read_file(article_id: int, ref: str, path: str, db: DB, user: CurrentUser):
    version = resolve_version(db, get_article(db, article_id, user), ref)
    # O arquivo é achado pela árvore da versão, nunca pelo hash direto: assim ninguém lê arquivo de artigo alheio.
    blob = versioning.blob_at(db, version.tree_hash, path)
    if blob is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"O arquivo {path} não existe nesta versão.")
    return Response(blob.content, media_type="text/plain; charset=utf-8" if blob.is_text else "application/octet-stream")


@router.get("/{article_id}/diff", response_model=DiffOut)
def diff(article_id: int, db: DB, user: CurrentUser, to: str, from_: str | None = Query(None, alias="from")):
    article = get_article(db, article_id, user)
    new = resolve_version(db, article, to)
    if from_:
        old = resolve_version(db, article, from_)
    elif new.parent_hash:
        old = db.get(Version, new.parent_hash)
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Essa é a primeira versão: não há versão anterior para comparar.")
    files = diff_trees(versioning.entries_of(db, old.tree_hash), versioning.entries_of(db, new.tree_hash), lambda h: db.get(Blob, h))
    return DiffOut(from_version=old.hash, to_version=new.hash, files=files)


@router.get("/{article_id}/versions/{ref}/document")
def read_document(article_id: int, ref: str, db: DB, user: CurrentUser):
    return loaded(db, get_article(db, article_id, user), ref).doc


@router.get("/{article_id}/versions/{ref}/images/{path:path}")
def read_image(article_id: int, ref: str, path: str, db: DB, user: CurrentUser):
    image = loaded(db, get_article(db, article_id, user), ref).image(path)
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"A imagem {path} não está nesta versão.")
    content, media = image
    return Response(content, media_type=media, headers=CACHE_FOREVER)


@router.get("/{article_id}/versions/{ref}/pdf")
def download_pdf(article_id: int, ref: str, db: DB, user: CurrentUser):
    article = get_article(db, article_id, user)
    version = loaded(db, article, ref)
    name = f"{slug(article.title)}-{version.version.hash[:7]}.pdf"
    return Response(version.pdf(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/{article_id}/versions/{ref}/pages")
def count_pages(article_id: int, ref: str, db: DB, user: CurrentUser):
    return {"pages": pdf_page_count(loaded(db, get_article(db, article_id, user), ref).pdf())}


@router.get("/{article_id}/versions/{ref}/pages/{number}.png")
def read_page(article_id: int, ref: str, number: int, db: DB, user: CurrentUser):
    """Uma página do PDF como imagem: a leitura no site é exatamente o PDF que se baixa."""
    pdf = loaded(db, get_article(db, article_id, user), ref).pdf()
    if not 1 <= number <= pdf_page_count(pdf):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Página não encontrada.")
    return Response(page_png(pdf, number - 1, PAGE_WIDTH), media_type="image/png", headers=CACHE_FOREVER)


@router.get("/{article_id}/versions/{ref}/zip")
def download_zip(article_id: int, ref: str, db: DB, user: CurrentUser):
    article = get_article(db, article_id, user)
    version = resolve_version(db, article, ref)
    entries = versioning.entries_of(db, version.tree_hash)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(entries):
            zf.writestr(path, db.get(Blob, entries[path]).content)
    name = f"{slug(article.title)}-{version.hash[:7]}.zip"
    return Response(buffer.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/{article_id}/versions/{ref}/references")
def list_references(article_id: int, ref: str, db: DB, user: CurrentUser):
    """Todas as referências do .bib, citadas ou não, com o texto e a citação no estilo do artigo."""
    current = loaded(db, get_article(db, article_id, user), ref)
    path = current.bib_path()
    text = decode_text(current.read(path)) if path in current.entries else ""
    style = citation_style(current.doc)
    numbers = {e["key"]: e.get("number") for e in current.doc.get("bibliography", [])}
    cited = Counter(k for span in walk_spans(current.doc) if span.get("kind") == "cite" for k in span.get("keys", []))
    entries = [
        {"key": c["key"], "type": c["type"], "fields": c["fields"], "text": entry_text(c, style),
         "label": entry_label(c, c["key"], style, numbers.get(c["key"])), "cited": cited.get(c["key"], 0)}
        for c in bib_chunks(text) if "key" in c
    ]
    return {"path": path, "style": style, "types": BIB_TYPES, "entries": entries}


# ---------- versões novas ----------

@router.post("/{article_id}/versions", response_model=VersionOut, status_code=status.HTTP_201_CREATED)
async def upload_version(
    article_id: int, db: DB, user: CurrentUser,
    file: UploadFile = File(..., description="Zip exportado do Overleaf"),
    message: str = Form(..., min_length=1, max_length=2000),
    base_version: str | None = Form(None, description="Versão em que você se baseou"),
):
    article = get_article(db, article_id, user)
    files = await read_zip(file)
    base = resolve_version(db, article, base_version.strip()).hash if base_version and base_version.strip() else None
    return save_version(db, article, files, message, base, user)


def compose(db, article: Article, data: DraftIn):
    """Os arquivos da versão nova: o .tex principal editado, as referências (se mudaram) e as imagens novas."""
    current = loaded(db, article, data.base_version)
    if data.source is not None:
        source = data.source
    elif data.document is not None:
        try:
            source = serialize_document(data.document)
        except (KeyError, TypeError, ValueError, IndexError):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Não consegui ler o documento enviado.") from None
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Envie o documento editado.")

    files = current.files()
    if data.references is not None:
        entries = clean_entries([r.model_dump() for r in data.references])
        path = current.bib_path()
        original = decode_text(files[path]) if path in files else ""
        text = write_bib(original, entries)
        if text != original and (entries or path in files):
            files[path] = text.encode("utf-8")
        if entries:
            source = ensure_bibliography(source, path)
    for image in data.images:
        if image.path in files:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Já existe um arquivo chamado {image.path}.")
        files[image.path] = pictures.figure(image.path, image.data)
    files[current.main] = source.encode("utf-8")
    return current, files


@router.post("/{article_id}/edits", response_model=VersionOut, status_code=status.HTTP_201_CREATED)
def save_edit(article_id: int, data: EditIn, db: DB, user: CurrentUser):
    article = get_article(db, article_id, user)
    current, files = compose(db, article, data)
    return save_version(db, article, files, data.message, current.version.hash, user)


@router.post("/{article_id}/preview")
def preview_draft(article_id: int, data: DraftIn, db: DB, user: CurrentUser):
    """O PDF do que está no editor, antes de salvar, como imagens das páginas."""
    _, files = compose(db, get_article(db, article_id, user), data)
    pdf = pdf_from_files(files)
    pages = (base64.b64encode(page_png(pdf, i, PAGE_WIDTH)).decode() for i in range(pdf_page_count(pdf)))
    return {"pages": [f"data:image/png;base64,{p}" for p in pages]}
