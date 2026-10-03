"""Ajuda para montar referências: conferir o formulário, ler BibTeX colado e buscar pelo DOI."""
import re

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.document.bibtex import clean_entries, entries_from_bibtex, make_key
from app.document.references import entry_label, entry_text
from app.schemas import ReferenceIn
from app.security import CurrentUser

router = APIRouter(prefix="/references", tags=["referências"])
STYLES = {"autor-data", "abnt", "numeric", "numeric-sorted"}
DOI = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)


class CheckIn(BaseModel):
    entry: ReferenceIn
    taken: list[str] = Field(default_factory=list, max_length=2000)
    style: str = "autor-data"


class BibtexIn(BaseModel):
    bibtex: str = Field(min_length=1, max_length=200_000)
    taken: list[str] = Field(default_factory=list, max_length=2000)
    style: str = "autor-data"


def shown(entry: dict, style: str) -> dict:
    style = style if style in STYLES else "autor-data"
    return {**entry, "text": entry_text(entry, style), "label": entry_label(entry, entry["key"], style), "cited": 0}


@router.post("/check")
def check(data: CheckIn, user: CurrentUser):
    """Confere uma referência preenchida no formulário e dá uma chave para ela, se ainda não tiver."""
    entry = data.entry.model_dump()
    if not entry["fields"].get("title", "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Escreva pelo menos o título da obra.")
    [clean] = clean_entries([entry])
    # Editando uma referência, ela mantém a chave (e as citações no texto continuam valendo).
    others = set(data.taken) - {entry["key"]}
    if not entry["key"] or clean["key"] in others:
        clean["key"] = make_key(clean["fields"], set(data.taken))
    return shown(clean, data.style)


@router.post("/parse")
def parse(data: BibtexIn, user: CurrentUser):
    """Lê referências em BibTeX, como as do botão "Citar" do Google Acadêmico."""
    found = entries_from_bibtex(data.bibtex, set(data.taken))
    if not found:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Não achei nenhuma referência nesse texto. Ele deve começar com @, como @article{...}.")
    return [shown(e, data.style) for e in found]


def fetch_bibtex(doi: str) -> str:
    """Pergunta ao doi.org pela referência em BibTeX (o serviço oficial dos DOIs responde nesse formato)."""
    response = httpx.get(f"https://doi.org/{doi}", headers={"Accept": "application/x-bibtex; charset=utf-8"},
                         follow_redirects=True, timeout=10)
    if response.status_code == 404:
        raise LookupError
    response.raise_for_status()
    return response.content.decode("utf-8", "replace")


@router.get("/doi")
def by_doi(user: CurrentUser, doi: str = Query(..., max_length=300), taken: list[str] = Query([]), style: str = "autor-data"):
    found = DOI.search(doi.strip())
    if not found:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Isso não parece um DOI. Ele começa com 10., como 10.1145/3290605.3300233.")
    code = found.group(0).rstrip(".,;")
    try:
        text = fetch_bibtex(code)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nenhuma obra tem esse DOI. Confira se ele foi copiado inteiro.")
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Não consegui falar com o doi.org agora. Tente de novo ou preencha a referência à mão.")
    entries = entries_from_bibtex(text, set(taken))
    if not entries:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "O doi.org respondeu num formato inesperado. Preencha a referência à mão.")
    entry = entries[0]
    entry["fields"].setdefault("doi", code)
    return shown(entry, style)
