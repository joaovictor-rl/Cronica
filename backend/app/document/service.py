import hashlib
import re
import threading
import unicodedata
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from reportlab.lib.units import cm
from sqlalchemy.orm import Session

from app import versioning
from app.document.blocks import find_main, parse_document
from app.document.images import displayable, resolve_image
from app.document.inline import plain_text
from app.document.pdf import build_pdf, layout_for
from app.document.references import annotate, load_bibliography
from app.ingest import decode_text
from app.models import Blob, Version

_pdf_cache: OrderedDict[str, bytes] = OrderedDict()
_pdf_lock = threading.Lock()


class NoMainFile(Exception):
    pass


@dataclass
class LoadedVersion:
    version: Version
    entries: dict[str, str]
    main: str
    doc: dict
    db: Session

    def read(self, path: str) -> bytes:
        return self.db.get(Blob, self.entries[path]).content

    def image(self, path: str) -> tuple[bytes, str] | None:
        real = resolve_image(path, self.main, self.entries)
        return displayable(self.read(real), self.entries[real]) if real else None

    def pdf(self) -> bytes:
        # Uma versão nunca muda, então o PDF dela pode ser guardado: a leitura pede uma página de cada vez.
        with _pdf_lock:
            if self.version.hash in _pdf_cache:
                _pdf_cache.move_to_end(self.version.hash)
                return _pdf_cache[self.version.hash]
        content = build_pdf(self.doc, lambda path: (self.image(path) or (None,))[0])
        with _pdf_lock:
            _pdf_cache[self.version.hash] = content
            while len(_pdf_cache) > 16:
                _pdf_cache.popitem(last=False)
        return content

    def files(self) -> dict[str, bytes]:
        return {path: self.read(path) for path in self.entries}

    def bib_path(self) -> str:
        return bib_path(self.doc, self.main, self.entries)


def bib_path(doc: dict, main: str, available) -> str:
    """O arquivo .bib do artigo: o do \\bibliography, outro .bib que exista, ou um novo referencias.bib."""
    folder = main.rsplit("/", 1)[0] + "/" if "/" in main else ""
    wanted = [name for block in doc["blocks"] if block["type"] == "references" for name in block.get("files", [])]
    if wanted:
        name = wanted[0]
        return folder + (name if name.endswith(".bib") else name + ".bib")
    existing = sorted(p for p in available if p.endswith(".bib"))
    return existing[0] if existing else folder + "referencias.bib"


def ensure_bibliography(source: str, bib_file: str) -> str:
    """Põe \\bibliography no fim do artigo, se ainda não houver, para as referências aparecerem."""
    if re.search(r"\\bibliography\{", source):
        return source
    stem = bib_file.rsplit("/", 1)[-1].removesuffix(".bib")
    style = "abntex2-alf" if "abntex2cite" in source else "plain"
    block = f"\\bibliographystyle{{{style}}}\n\\bibliography{{{stem}}}\n\n"
    end = source.rfind("\\end{document}")
    return source[:end] + block + source[end:] if end != -1 else source + "\n" + block


def document_from_files(files: dict[str, bytes]) -> tuple[dict, Callable]:
    """Documento anotado e leitor de imagens a partir de arquivos soltos (para a prévia, antes de salvar)."""
    main = find_main(list(files), lambda path: decode_text(files[path]))
    if not main:
        raise NoMainFile()
    doc = parse_document(decode_text(files[main]))
    bibs = {path: files[path] for path in files if path.endswith(".bib")}
    annotate(doc, load_bibliography(doc, main, bibs))
    doc["main"] = main
    page_layout(doc)

    def image(path):
        real = resolve_image(path, main, files)
        if not real:
            return None
        return displayable(files[real], hashlib.sha256(files[real]).hexdigest())[0]
    return doc, image


def pdf_from_files(files: dict[str, bytes]) -> bytes:
    doc, image = document_from_files(files)
    return build_pdf(doc, image)


def load_version(db: Session, version: Version) -> LoadedVersion:
    entries = versioning.entries_of(db, version.tree_hash)
    read = lambda path: db.get(Blob, entries[path]).content
    main = find_main(list(entries), lambda path: decode_text(read(path)))
    if not main:
        raise NoMainFile()
    doc = parse_document(decode_text(read(main)))
    bibs = {path: read(path) for path in entries if path.endswith(".bib")}
    annotate(doc, load_bibliography(doc, main, bibs))
    doc["main"] = main
    page_layout(doc)
    return LoadedVersion(version, entries, main, doc, db)


def page_layout(doc: dict) -> None:
    """O formato e as margens da página, para o editor ficar com a cara do PDF."""
    layout = layout_for(doc)
    doc["format"] = layout.kind
    doc["margins_cm"] = [round(side / cm, 2) for side in (layout.top, layout.right, layout.bottom, layout.left)]


def title_of(source: str) -> str | None:
    doc = parse_document(source)
    return plain_text(doc["meta"]["title"]["spans"]) if "title" in doc.get("meta", {}) else None


def slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()[:60] or "artigo"
