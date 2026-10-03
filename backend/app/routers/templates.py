"""Modelos de artigo: a lista e uma prévia da primeira página de cada um. Públicos: não têm nada de ninguém."""
from functools import cache

from fastapi import APIRouter, HTTPException, Response, status

from app.document.images import page_png
from app.document.inline import plain_text
from app.document.service import document_from_files, pdf_from_files
from app.document.templates import BY_ID, TEMPLATES

router = APIRouter(prefix="/templates", tags=["modelos"])


@cache
def example(template_id: str) -> dict[str, bytes]:
    return BY_ID[template_id].build("Título do seu artigo", "Seu nome")


@router.get("")
def list_templates():
    out = []
    for t in TEMPLATES:
        doc, _ = document_from_files(example(t.id))
        sections = [plain_text(b["spans"]) for b in doc["blocks"] if b["type"] == "heading" and b.get("level") == 1]
        out.append({"id": t.id, "name": t.name, "description": t.description, "use_for": t.use_for,
                    "language": t.language, "sections": sections})
    return out


@cache
def preview_png(template_id: str) -> bytes:
    return page_png(pdf_from_files(example(template_id)), 0, 446)


@router.get("/{template_id}/preview.png")
def preview(template_id: str):
    if template_id not in BY_ID:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo não encontrado.")
    return Response(preview_png(template_id), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
