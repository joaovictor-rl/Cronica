"""Gera o PDF de uma versão a partir dos blocos, sem precisar de LaTeX instalado.

É uma aproximação do layout do LaTeX: título, resumo, seções numeradas, figuras, tabelas,
citações e referências. Para o layout exato da revista, o projeto pode ser aberto no Overleaf.
"""
import io
import re
from collections.abc import Callable

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.document.inline import parse_inline, plain_text

MARGIN = 2.5 * cm
TEXT_WIDTH = A4[0] - 2 * MARGIN
SERIF = "Times-Roman"

BODY = ParagraphStyle("body", fontName=SERIF, fontSize=11.5, leading=15, alignment=TA_JUSTIFY, firstLineIndent=0.9 * cm, spaceAfter=4)
TITLE = ParagraphStyle("title", fontName="Times-Bold", fontSize=16, leading=20, alignment=TA_CENTER, spaceAfter=10)
AUTHORS = ParagraphStyle("authors", fontName=SERIF, fontSize=11.5, leading=15, alignment=TA_CENTER, spaceAfter=4)
ADDRESS = ParagraphStyle("address", fontName=SERIF, fontSize=10, leading=13, alignment=TA_CENTER, spaceAfter=14)
ABSTRACT = ParagraphStyle("abstract", parent=BODY, fontSize=10.5, leading=13.5, leftIndent=1 * cm, rightIndent=1 * cm, firstLineIndent=0, spaceAfter=8)
HEADINGS = {
    0: ParagraphStyle("h0", fontName="Times-Bold", fontSize=14, leading=18, spaceBefore=14, spaceAfter=6, keepWithNext=1),
    1: ParagraphStyle("h1", fontName="Times-Bold", fontSize=13, leading=17, spaceBefore=12, spaceAfter=5, keepWithNext=1),
    2: ParagraphStyle("h2", fontName="Times-Bold", fontSize=12, leading=15, spaceBefore=9, spaceAfter=4, keepWithNext=1),
    3: ParagraphStyle("h3", fontName="Times-Bold", fontSize=11.5, leading=15, spaceBefore=8, spaceAfter=3, keepWithNext=1),
    4: ParagraphStyle("h4", fontName="Times-BoldItalic", fontSize=11.5, leading=15, spaceBefore=6, spaceAfter=2, keepWithNext=1),
}
CAPTION = ParagraphStyle("caption", fontName=SERIF, fontSize=10, leading=12.5, alignment=TA_CENTER, spaceBefore=4, spaceAfter=10)
SUBCAPTION = ParagraphStyle("subcaption", parent=CAPTION, fontSize=9, leading=11, spaceBefore=2, spaceAfter=4)
CELL = ParagraphStyle("cell", fontName=SERIF, fontSize=9, leading=11, alignment=TA_LEFT)
NOTE = ParagraphStyle("note", fontName=SERIF, fontSize=8.5, leading=10.5, alignment=TA_CENTER, spaceAfter=10)
FOOTNOTE = ParagraphStyle("footnote", fontName=SERIF, fontSize=8.5, leading=10.5, textColor=colors.HexColor("#444444"), spaceAfter=4)
REFERENCE = ParagraphStyle("reference", fontName=SERIF, fontSize=10, leading=12.5, leftIndent=0.6 * cm, firstLineIndent=-0.6 * cm, spaceAfter=5, alignment=TA_LEFT)
ALIGN = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}
LETTERS = "abcdefghijklmnopqrstuvwxyz"


def esc(text: str) -> str:
    # As fontes padrão do PDF usam o alfabeto do Windows (cp1252), que cobre o português.
    text = text.encode("cp1252", "replace").decode("cp1252")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def markup(spans: list[dict]) -> str:
    out = []
    for span in spans:
        if span.get("br"):
            out.append("<br/>")
            continue
        if "t" in span:
            piece = esc(span["t"])
        else:
            kind, label = span.get("kind"), span.get("label", "")
            if kind in ("comment", "label"):
                continue
            if kind in ("footnote", "sup"):
                piece = f"<super>{esc(label)}</super>"
            elif kind == "math":
                piece = f"<i>{esc(label)}</i>"
            elif kind == "url":
                piece = f'<link href="{esc(span.get("href", label))}" color="#1f5f5b">{esc(label)}</link>'
            else:
                piece = esc(label)
        if span.get("i"):
            piece = f"<i>{piece}</i>"
        if span.get("b"):
            piece = f"<b>{piece}</b>"
        out.append(piece)
    return "".join(out).strip()


def footnotes(spans: list[dict]) -> list:
    return [Paragraph(f"<super>{esc(s['label'])}</super> {esc(s.get('text', ''))}", FOOTNOTE)
            for s in spans if s.get("kind") == "footnote"]


def scaled_image(content: bytes, max_width: float, max_height: float) -> Image:
    width, height = PILImage.open(io.BytesIO(content)).size
    scale = min(max_width / width, max_height / height)
    return Image(io.BytesIO(content), width=width * scale, height=height * scale)


def figure(block: dict, load_image: Callable[[str], bytes | None]) -> list:
    loaded = [(image, load_image(image["path"])) for image in block["images"]]
    loaded = [(image, content) for image, content in loaded if content]
    parts = []
    if len(loaded) == 1:
        parts.append(scaled_image(loaded[0][1], TEXT_WIDTH * 0.95, 13 * cm))
    elif loaded:
        per_row = 3 if len(loaded) > 4 else 2
        cell_width = TEXT_WIDTH / per_row
        cells = []
        for i, (image, content) in enumerate(loaded):
            cell = [scaled_image(content, cell_width - 0.4 * cm, 5 * cm)]
            if image.get("caption"):
                cell.append(Paragraph(f"({LETTERS[i]}) {markup(image['caption'])}", SUBCAPTION))
            cells.append(cell)
        rows = [cells[i:i + per_row] for i in range(0, len(cells), per_row)]
        rows[-1] += [""] * (per_row - len(rows[-1]))
        grid = Table(rows, colWidths=[cell_width] * per_row)
        grid.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
        parts.append(grid)
    if block.get("caption"):
        parts.append(Paragraph(f"<b>Figura {block.get('number', '')}.</b> {markup(block['caption'])}", CAPTION))
    return [KeepTogether(parts)] if parts else []


def column_widths(block: dict) -> list[float]:
    columns = block.get("columns") or []
    count = max((len(r) for r in block["rows"]), default=0)
    columns = (columns + [{"align": "left"}] * count)[:count]
    widths = []
    for index, column in enumerate(columns):
        if column.get("width_cm"):
            widths.append(column["width_cm"] * cm)
        elif column.get("grow"):
            widths.append(None)
        else:
            longest = max((stringWidth(plain_text(row[index]), "Times-Bold", 9) for row in block["rows"] if index < len(row)), default=20)
            widths.append(min(longest + 16, TEXT_WIDTH / 2))
    fixed = sum(w for w in widths if w)
    growing = widths.count(None)
    rest = max(TEXT_WIDTH - fixed, 2 * cm * growing)
    widths = [w if w else rest / growing for w in widths]
    total = sum(widths)
    return [w * TEXT_WIDTH / total for w in widths] if total > TEXT_WIDTH else widths


def table(block: dict) -> list:
    parts = []
    if block.get("caption"):
        parts.append(Paragraph(f"<b>Tabela {block.get('number', '')}.</b> {markup(block['caption'])}", CAPTION))
    if block["rows"]:
        widths = column_widths(block)
        aligns = [ALIGN[c.get("align", "left")] for c in (block.get("columns") or [])] + [TA_LEFT] * len(widths)
        data = [
            [Paragraph(markup(cell), ParagraphStyle("c", parent=CELL, alignment=aligns[i])) for i, cell in enumerate(row)]
            + [""] * (len(widths) - len(row))
            for row in block["rows"]
        ]
        grid = Table(data, colWidths=widths, repeatRows=1)
        grid.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        parts.append(grid)
    if block.get("note"):
        parts.append(Paragraph(markup(block["note"]), NOTE))
    else:
        parts.append(Spacer(1, 8))
    return [KeepTogether(parts)]


def raw_text(src: str) -> str:
    inner = re.sub(r"^\\begin\{[^}]*\}(\{[^}]*\}|\[[^\]]*\])*|\\end\{[^}]*\}$", "", src.strip())
    return markup(parse_inline(inner))


def build_pdf(doc: dict, load_image: Callable[[str], bytes | None]) -> bytes:
    story = []
    meta = doc.get("meta", {})
    if "title" in meta:
        story.append(Paragraph(markup(meta["title"]["spans"]), TITLE))
    if "author" in meta:
        story.append(Paragraph(markup(meta["author"]["spans"]), AUTHORS))
    if "address" in meta:
        story.append(Paragraph(markup(meta["address"]["spans"]), ADDRESS))
    elif meta:
        story.append(Spacer(1, 10))

    abstract_label = {"abstract": "Abstract" if doc.get("language") == "en" else "Resumo", "resumo": "Resumo",
                      "IEEEkeywords": "Index Terms"}
    for block in doc.get("blocks", []):
        kind = block["type"]
        if kind == "paragraph":
            text = markup(block["spans"])
            if text:
                story.append(Paragraph(text, BODY))
                story += footnotes(block["spans"])
        elif kind == "heading":
            number = f"{block['number']}. " if block.get("number") else ""
            story.append(Paragraph(number + markup(block["spans"]), HEADINGS.get(block.get("level", 1), HEADINGS[1])))
        elif kind == "abstract":
            label = abstract_label.get(block.get("env", "abstract").rstrip("*"), "Resumo")
            for i, paragraph in enumerate(block["paragraphs"]):
                prefix = f"<b>{label}.</b> " if i == 0 else ""
                story.append(Paragraph(prefix + markup(paragraph), ABSTRACT))
        elif kind == "list":
            numbered = block.get("env") == "enumerate"
            items = [ListItem(Paragraph(markup(item["spans"]), ParagraphStyle("li", parent=BODY, firstLineIndent=0)))
                     for item in block["items"]]
            story.append(ListFlowable(items, bulletType="1" if numbered else "bullet", start="1" if numbered else "•",
                                      leftIndent=0.9 * cm, bulletFontName=SERIF, bulletFontSize=10))
            story.append(Spacer(1, 4))
        elif kind == "figure":
            story += figure(block, load_image)
        elif kind == "table":
            story += table(block)
        elif kind == "raw":
            text = raw_text(block["src"])
            if text:
                story.append(Paragraph(text, ParagraphStyle("raw", parent=BODY, alignment=TA_CENTER, firstLineIndent=0)))
        elif kind == "references" and doc.get("bibliography"):
            story.append(Paragraph(esc(doc.get("references_title", "Referências")), HEADINGS[1]))
            story += [Paragraph(esc((f"[{entry['number']}] " if entry.get("number") else "") + entry["text"]), REFERENCE)
                      for entry in doc["bibliography"]]

    buffer = io.BytesIO()
    title = plain_text(meta["title"]["spans"]) if "title" in meta else "Artigo"
    pdf = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                            bottomMargin=MARGIN, title=title, author="Crônica")
    pdf.build(story or [Paragraph("Documento vazio.", BODY)], onFirstPage=page_number, onLaterPages=page_number)
    return buffer.getvalue()


def page_number(canvas, doc):
    canvas.setFont(SERIF, 9)
    canvas.drawCentredString(A4[0] / 2, 1.3 * cm, str(doc.page))
