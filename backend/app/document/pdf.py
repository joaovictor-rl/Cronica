"""Gera o PDF de uma versão a partir dos blocos, sem precisar de LaTeX instalado.

Cada formato tem as suas regras de página (veja layout_for): ABNT, SBC, IEEE (em duas colunas) e,
para qualquer outro artigo, as medidas padrão do LaTeX. É uma aproximação do que o LaTeX faria;
para o layout exato, o projeto pode ser aberto no Overleaf.
"""
import io
import re
from collections.abc import Callable
from dataclasses import dataclass

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, inch, mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    FrameBreak,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.document.inline import parse_inline, plain_text

ALIGN = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}
LETTERS = "abcdefghijklmnopqrstuvwxyz"
COLUMN_GAP = 0.42 * cm


@dataclass
class Layout:
    kind: str          # "abnt", "sbc", "ieee" ou "latex" (qualquer outro artigo)
    top: float         # margens
    bottom: float
    left: float
    right: float
    size: float        # fonte do texto, em pontos
    leading: float     # distância entre as linhas
    indent: float      # recuo da primeira linha do parágrafo
    paragraph_space: float = 0
    columns: int = 1
    english: bool = False

    @property
    def width(self) -> float:
        return A4[0] - self.left - self.right

    @property
    def column_width(self) -> float:
        return (self.width - COLUMN_GAP * (self.columns - 1)) / self.columns


UNITS = {"cm": cm, "mm": mm, "in": inch, "pt": 1}


def geometry(preamble: str) -> dict[str, float]:
    """As margens pedidas em \\usepackage[top=3cm, ...]{geometry}."""
    found = re.search(r"\\usepackage\[([^\]]*)\]\{geometry\}", preamble)
    sizes = {}
    for key, number, unit in re.findall(r"(\w+)\s*=\s*([\d.]+)\s*(cm|mm|in|pt)", found.group(1) if found else ""):
        value = float(number) * UNITS[unit]
        for side in {"margin": ("top", "bottom", "left", "right"), "hmargin": ("left", "right"),
                     "vmargin": ("top", "bottom")}.get(key, (key,)):
            sizes[side] = value
    return sizes


def layout_for(doc: dict) -> Layout:
    preamble = doc.get("preamble", "")
    english = doc.get("language") == "en" and not re.search(r"brazil|portug", preamble)
    margins = geometry(preamble)

    def page(top, bottom, left, right):
        return {side: margins.get(side, default) for side, default in
                (("top", top), ("bottom", bottom), ("left", left), ("right", right))}

    if doc.get("citation_style") == "abnt" or "abntex2" in preamble:
        # NBR 14724: margens de 3 cm (em cima e à esquerda) e 2 cm, fonte 12, espaço 1,5 e recuo de 1,25 cm.
        return Layout("abnt", **page(3 * cm, 2 * cm, 3 * cm, 2 * cm), size=12, leading=18, indent=1.25 * cm)
    if "IEEEtran" in preamble:
        return Layout("ieee", top=1.9 * cm, bottom=4.3 * cm, left=1.43 * cm, right=1.43 * cm, size=10, leading=12,
                      indent=0.35 * cm, columns=2, english=english)
    if "sbc-template" in preamble:  # as medidas do sbc-template.sty
        return Layout("sbc", top=3.5 * cm, bottom=2.5 * cm, left=3 * cm, right=3 * cm, size=12, leading=14,
                      indent=1.27 * cm, paragraph_space=6, english=english)
    found = re.search(r"\\documentclass\[[^\]]*?(10|11|12)pt", preamble)
    size = int(found.group(1)) if found else 10
    side = {10: 4.4, 11: 4.1, 12: 3.6}[size] * cm  # a largura de texto padrão do LaTeX em A4
    return Layout("latex", **page(3.5 * cm, 4 * cm, side, side), size=size, leading=size * 1.2,
                  indent=1.5 * size, english=english)


class Styles:
    """Os estilos de texto de um formato."""

    def __init__(self, layout: Layout):
        size, kind = layout.size, layout.kind
        small = size - 2
        self.body = ParagraphStyle("body", fontName="Times-Roman", fontSize=size, leading=layout.leading,
                                   alignment=TA_JUSTIFY, firstLineIndent=layout.indent, spaceAfter=layout.paragraph_space)
        title_size = {"abnt": 12, "sbc": 16, "ieee": 24, "latex": 17}[kind]
        self.title = ParagraphStyle("title", fontName="Times-Roman" if kind in ("ieee", "latex") else "Times-Bold",
                                    fontSize=title_size, leading=title_size * 1.25, alignment=TA_CENTER, spaceAfter=10)
        self.authors = ParagraphStyle("authors", parent=self.body, fontName="Times-Bold" if kind == "sbc" else "Times-Roman",
                                      fontSize=11 if kind == "ieee" else max(size, 12), leading=max(size, 12) * 1.2,
                                      alignment=TA_CENTER, firstLineIndent=0, spaceAfter=4)
        self.address = ParagraphStyle("address", parent=self.authors, fontName="Times-Roman",
                                      fontSize=size if kind == "sbc" else small, spaceAfter=14)
        single = size * 1.2  # espaço simples
        if kind == "abnt":
            self.abstract = ParagraphStyle("abstract", parent=self.body, leading=single, firstLineIndent=0, spaceAfter=6)
        elif kind == "sbc":
            self.abstract = ParagraphStyle("abstract", parent=self.body, fontName="Times-Italic", leftIndent=0.8 * cm,
                                           rightIndent=0.8 * cm, firstLineIndent=0, spaceBefore=6, spaceAfter=6)
        elif kind == "ieee":
            self.abstract = ParagraphStyle("abstract", parent=self.body, fontName="Times-Bold", fontSize=9, leading=10.5,
                                           firstLineIndent=layout.indent, spaceAfter=6)
        else:
            self.abstract = ParagraphStyle("abstract", parent=self.body, fontSize=small, leading=small * 1.2,
                                           leftIndent=1 * cm, rightIndent=1 * cm, spaceAfter=4)
        self.abstract_title = ParagraphStyle("abstract-title", fontName="Times-Bold", fontSize=size if kind == "abnt" else small,
                                             leading=single, alignment=TA_CENTER, spaceBefore=6, spaceAfter=6)
        self.headings = self.heading_styles(layout)
        if kind == "sbc":
            self.caption = ParagraphStyle("caption", fontName="Helvetica-Bold", fontSize=10, leading=12, alignment=TA_CENTER,
                                          leftIndent=0.8 * cm, rightIndent=0.8 * cm, spaceBefore=6, spaceAfter=6)
        else:
            caption_size = 8 if kind == "ieee" else 10 if kind == "abnt" else size
            self.caption = ParagraphStyle("caption", fontName="Times-Roman", fontSize=caption_size, leading=caption_size * 1.2,
                                          alignment=TA_CENTER, spaceBefore=6, spaceAfter=6)
        self.subcaption = ParagraphStyle("subcaption", parent=self.caption, fontSize=self.caption.fontSize - 1,
                                         leading=(self.caption.fontSize - 1) * 1.2, spaceBefore=2, spaceAfter=4)
        cell = 8 if kind == "ieee" else 10 if kind == "abnt" else 9
        self.cell = ParagraphStyle("cell", fontName="Times-Roman", fontSize=cell, leading=cell * 1.2)
        self.note = ParagraphStyle("note", parent=self.cell, alignment=TA_LEFT if kind == "abnt" else TA_CENTER, spaceAfter=10)
        self.footnote = ParagraphStyle("footnote", fontName="Times-Roman", fontSize=small, leading=small * 1.2,
                                       textColor=colors.HexColor("#444444"), spaceAfter=4)
        self.list_item = ParagraphStyle("item", parent=self.body, firstLineIndent=0)
        self.raw = ParagraphStyle("raw", parent=self.body, alignment=TA_CENTER, firstLineIndent=0)
        if kind == "abnt":  # NBR 6023: alinhadas à esquerda, espaço simples, uma linha em branco entre elas
            self.reference = ParagraphStyle("reference", fontName="Times-Roman", fontSize=size, leading=single, spaceAfter=single)
        else:
            ref_size = 8 if kind == "ieee" else size
            self.reference = ParagraphStyle("reference", fontName="Times-Roman", fontSize=ref_size, leading=ref_size * 1.2,
                                            leftIndent=0.6 * cm, firstLineIndent=-0.6 * cm, spaceAfter=6 if kind == "sbc" else 3)

    @staticmethod
    def heading_styles(layout: Layout) -> dict[int, ParagraphStyle]:
        size, kind = layout.size, layout.kind

        def style(level, font, font_size, before, after, align=TA_LEFT):
            return ParagraphStyle(f"h{level}", fontName=font, fontSize=font_size, leading=font_size * 1.3, alignment=align,
                                  spaceBefore=before, spaceAfter=after, keepWithNext=1)
        if kind == "abnt":  # títulos do mesmo tamanho do texto, separados por uma linha em branco
            fonts = ["Times-Bold", "Times-Bold", "Times-Roman", "Times-Bold", "Times-Italic"]
            return {level: style(level, fonts[level], size, layout.leading, layout.leading) for level in range(5)}
        if kind == "sbc":
            sizes = [16, 13, 12, 12, 12]
            return {level: style(level, "Times-Bold", sizes[level], 12, 6) for level in range(5)}
        if kind == "ieee":
            return {0: style(0, "Times-Roman", 10, 10, 5, TA_CENTER), 1: style(1, "Times-Roman", 10, 10, 5, TA_CENTER),
                    2: style(2, "Times-Italic", 10, 6, 3), 3: style(3, "Times-Italic", 10, 4, 2), 4: style(4, "Times-Italic", 10, 4, 2)}
        sizes = [20, size * 1.44, size * 1.2, size, size]
        return {level: style(level, "Times-Bold", sizes[level], sizes[level] * 0.9, sizes[level] * 0.5) for level in range(5)}


def esc(text: str) -> str:
    # As fontes padrão do PDF usam o alfabeto do Windows (cp1252), que cobre o português.
    text = text.encode("cp1252", "replace").decode("cp1252")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def markup(spans: list[dict], upper: bool = False) -> str:
    out = []
    for span in spans:
        if span.get("br"):
            out.append("<br/>")
            continue
        if "t" in span:
            piece = esc(span["t"].upper() if upper else span["t"])
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


def roman(number: int) -> str:
    out = ""
    for value, letters in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while number >= value:
            out, number = out + letters, number - value
    return out


def heading_text(block: dict, layout: Layout) -> str:
    level, number = block.get("level", 1), block.get("number")
    if layout.kind == "abnt":  # 1 SEÇÃO PRIMÁRIA, 1.1 SEÇÃO SECUNDÁRIA, 1.1.1 Seção terciária
        text = markup(block["spans"], upper=level <= 2)
        return f"{number} {text}" if number else text
    if layout.kind == "ieee":  # I. INTRODUCTION, A. Subseção, 1) Subsubseção:
        text = markup(block["spans"], upper=level <= 1)
        if not number:
            return text
        last = int(number.split(".")[-1])
        return {1: f"{roman(last)}. {text}", 2: f"{LETTERS[last - 1].upper()}. {text}"}.get(level, f"{last}) {text}:")
    text = markup(block["spans"])
    if not number:
        return text
    return f"{number}. {text}" if layout.kind == "sbc" else f"{number} {text}"


def caption_label(kind: str, number: str, layout: Layout) -> str:
    """Figura 1 – (ABNT), Figura 1. (SBC), Fig. 1. e TABLE I (IEEE), Figura 1: (LaTeX)."""
    word = {"figure": "Figure" if layout.english else "Figura", "table": "Table" if layout.english else "Tabela"}[kind]
    if layout.kind == "abnt":
        return f"{word} {number} – "
    if layout.kind == "ieee":
        return f"Fig. {number}. " if kind == "figure" else f"TABLE {roman(int(number or 0))}<br/>"
    if layout.kind == "sbc":
        return f"{word} {number}. "
    return f"{word} {number}: "


def footnotes(spans: list[dict], styles: Styles) -> list:
    return [Paragraph(f"<super>{esc(s['label'])}</super> {esc(s.get('text', ''))}", styles.footnote)
            for s in spans if s.get("kind") == "footnote"]


def scaled_image(content: bytes, max_width: float, max_height: float) -> Image:
    width, height = PILImage.open(io.BytesIO(content)).size
    scale = min(max_width / width, max_height / height)
    return Image(io.BytesIO(content), width=width * scale, height=height * scale)


def figure(block: dict, load_image: Callable[[str], bytes | None], layout: Layout, styles: Styles) -> list:
    width = layout.column_width
    loaded = [(image, load_image(image["path"])) for image in block["images"]]
    loaded = [(image, content) for image, content in loaded if content]
    images = []
    if len(loaded) == 1:
        images.append(scaled_image(loaded[0][1], width * 0.95, 13 * cm))
    elif loaded:
        per_row = 3 if len(loaded) > 4 else 2
        cell_width = width / per_row
        cells = []
        for i, (image, content) in enumerate(loaded):
            cell = [scaled_image(content, cell_width - 0.4 * cm, 5 * cm)]
            if image.get("caption"):
                cell.append(Paragraph(f"({LETTERS[i]}) {markup(image['caption'])}", styles.subcaption))
            cells.append(cell)
        rows = [cells[i:i + per_row] for i in range(0, len(cells), per_row)]
        rows[-1] += [""] * (per_row - len(rows[-1]))
        grid = Table(rows, colWidths=[cell_width] * per_row)
        grid.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
        images.append(grid)
    caption = []
    if block.get("caption"):
        caption.append(Paragraph(caption_label("figure", block.get("number", ""), layout) + markup(block["caption"]), styles.caption))
    parts = caption + images if layout.kind == "abnt" else images + caption  # na ABNT a legenda vem em cima
    return [KeepTogether(parts)] if parts else []


def column_widths(block: dict, total_width: float) -> list[float]:
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
            widths.append(min(longest + 16, total_width / 2))
    fixed = sum(w for w in widths if w)
    growing = widths.count(None)
    rest = max(total_width - fixed, 2 * cm * growing)
    widths = [w if w else rest / growing for w in widths]
    total = sum(widths)
    return [w * total_width / total for w in widths] if total > total_width else widths


def table(block: dict, layout: Layout, styles: Styles) -> list:
    parts = []
    if block.get("caption"):
        parts.append(Paragraph(caption_label("table", block.get("number", ""), layout) + markup(block["caption"]), styles.caption))
    if block["rows"]:
        widths = column_widths(block, layout.column_width)
        aligns = [ALIGN[c.get("align", "left")] for c in (block.get("columns") or [])] + [TA_LEFT] * len(widths)
        data = [
            [Paragraph(markup(cell), ParagraphStyle("c", parent=styles.cell, alignment=aligns[i])) for i, cell in enumerate(row)]
            + [""] * (len(widths) - len(row))
            for row in block["rows"]
        ]
        if layout.kind == "abnt":  # tabelas abertas dos lados (norma do IBGE): só linhas horizontais
            lines = [("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black), ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                     ("LINEBELOW", (0, -1), (-1, -1), 0.8, colors.black)]
        else:
            lines = [("GRID", (0, 0), (-1, -1), 0.5, colors.black)]
        grid = Table(data, colWidths=widths, repeatRows=1)
        grid.setStyle(TableStyle(lines + [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        parts.append(grid)
    if block.get("note"):
        parts.append(Paragraph(markup(block["note"]), styles.note))
    else:
        parts.append(Spacer(1, 8))
    return [KeepTogether(parts)]


def raw_text(src: str) -> str:
    inner = re.sub(r"^\\begin\{[^}]*\}(\{[^}]*\}|\[[^\]]*\])*|\\end\{[^}]*\}$", "", src.strip())
    return markup(parse_inline(inner))


def abstract(block: dict, layout: Layout, styles: Styles) -> list:
    env = block.get("env", "abstract").rstrip("*")
    if env == "IEEEkeywords":
        label = "Index Terms" if layout.english else "Palavras-chave"
    elif env == "resumo" or (env == "abstract" and not layout.english and layout.kind != "sbc"):
        label = "Resumo"
    else:
        label = "Abstract"
    paragraphs = [markup(p) for p in block["paragraphs"]]
    if layout.kind in ("abnt", "latex"):  # o nome em cima, centralizado
        title = label.upper() if layout.kind == "abnt" else label
        return [Paragraph(title, styles.abstract_title)] + [Paragraph(p, styles.abstract) for p in paragraphs]
    prefix = f"<b><i>{label}</i>—</b>" if layout.kind == "ieee" else f"<b><i>{label}.</i></b> "
    return [Paragraph((prefix if i == 0 else "") + p, styles.abstract) for i, p in enumerate(paragraphs)]


def references(doc: dict, layout: Layout, styles: Styles) -> list:
    title = doc.get("references_title", "Referências")
    if layout.kind in ("abnt", "ieee"):
        heading = ParagraphStyle("refs", parent=styles.headings[1], alignment=TA_CENTER)
        out = [Paragraph(esc(title.upper()), heading)]
    else:
        out = [Paragraph(esc(title), styles.headings[1])]
    tag = "b" if layout.kind == "abnt" else "i"  # o destaque: negrito na ABNT, itálico nos outros
    for entry in doc["bibliography"]:
        text = esc(entry["text"])
        highlight = esc(entry.get("emphasis") or "")
        if highlight and highlight in text:
            at = text.rfind(highlight)
            text = f"{text[:at]}<{tag}>{highlight}</{tag}>{text[at + len(highlight):]}"
        number = f"[{entry['number']}] " if entry.get("number") else ""
        out.append(Paragraph(number + text, styles.reference))
    return out


def build_pdf(doc: dict, load_image: Callable[[str], bytes | None]) -> bytes:
    layout = layout_for(doc)
    styles = Styles(layout)
    header = []
    meta = doc.get("meta", {})
    if "title" in meta:
        header.append(Paragraph(markup(meta["title"]["spans"]), styles.title))
    if "author" in meta:
        header.append(Paragraph(markup(meta["author"]["spans"]), styles.authors))
    if "address" in meta:
        header.append(Paragraph(markup(meta["address"]["spans"]), styles.address))
    elif meta:
        header.append(Spacer(1, 10))

    story = []
    for block in doc.get("blocks", []):
        kind = block["type"]
        if kind == "paragraph":
            text = markup(block["spans"])
            if text:
                story.append(Paragraph(text, styles.body))
                story += footnotes(block["spans"], styles)
        elif kind == "heading":
            level = block.get("level", 1)
            story.append(Paragraph(heading_text(block, layout), styles.headings.get(level, styles.headings[1])))
        elif kind == "abstract":
            story += abstract(block, layout, styles)
        elif kind == "list":
            numbered = block.get("env") == "enumerate"
            items = [ListItem(Paragraph(markup(item["spans"]), styles.list_item)) for item in block["items"]]
            story.append(ListFlowable(items, bulletType="1" if numbered else "bullet", start="1" if numbered else "•",
                                      leftIndent=layout.indent, bulletFontName="Times-Roman", bulletFontSize=layout.size - 1))
            story.append(Spacer(1, 4))
        elif kind == "figure":
            story += figure(block, load_image, layout, styles)
        elif kind == "table":
            story += table(block, layout, styles)
        elif kind == "raw":
            text = raw_text(block["src"])
            if text:
                story.append(Paragraph(text, styles.raw))
        elif kind == "references" and doc.get("bibliography"):
            story += references(doc, layout, styles)
    if not header and not story:
        story = [Paragraph("Documento vazio.", styles.body)]

    buffer = io.BytesIO()
    title = plain_text(meta["title"]["spans"]) if "title" in meta else "Artigo"
    pdf = BaseDocTemplate(buffer, pagesize=A4, title=title, author="Crônica")
    if layout.columns > 1:
        # Duas colunas: na primeira página, o título ocupa a largura toda e as colunas começam embaixo dele.
        height = sum(f.wrap(layout.width, A4[1])[1] + f.getSpaceBefore() + f.getSpaceAfter() for f in header) + 12
        pdf.addPageTemplates([page_template("first", layout, height), page_template("later", layout, 0)])
        story = [NextPageTemplate("later"), *header, FrameBreak(), *story]
    else:
        pdf.addPageTemplates([page_template("page", layout, 0)])
        story = header + story
    pdf.build(story)
    return buffer.getvalue()


def page_template(name: str, layout: Layout, header_height: float) -> PageTemplate:
    def frame(x, y, width, height, id):
        return Frame(x, y, width, height, id=id, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    top = A4[1] - layout.top
    frames = [frame(layout.left, top - header_height, layout.width, header_height, "header")] if header_height else []
    frames += [frame(layout.left + i * (layout.column_width + COLUMN_GAP), layout.bottom, layout.column_width,
                     top - header_height - layout.bottom, f"column{i}") for i in range(layout.columns)]
    return PageTemplate(name, frames, onPage=lambda canvas, doc: page_number(canvas, doc, layout))


def page_number(canvas, doc, layout: Layout):
    if layout.kind in ("sbc", "ieee"):  # os dois modelos pedem páginas sem número
        return
    canvas.setFont("Times-Roman", 10)
    if layout.kind == "abnt":  # no canto superior direito, a 2 cm das bordas
        canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 2 * cm, str(doc.page))
    else:
        canvas.drawCentredString(A4[0] / 2, 1.3 * cm, str(doc.page))
