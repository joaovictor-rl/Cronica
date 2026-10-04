"""As regras de página e de referência de cada formato (ABNT, SBC, IEEE e LaTeX comum)."""
import io

import pypdfium2 as pdfium
import pytest
from reportlab.lib.units import cm

from app.diff.bib import parse_bib
from app.document.blocks import parse_document, serialize_document
from app.document.pdf import layout_for
from app.document.references import format_abnt
from app.document.service import pdf_from_files
from app.document.templates import TEMPLATES

BIB = r"""
@inproceedings{evento, author={Denise Oliveira and José Borges}, title={Perspectivas digitais},
  booktitle={Anais do I Workshop de Informática na Educação Inclusiva}, location={Rio de Janeiro}, address={Porto Alegre},
  publisher={SBC}, year={2024}, pages={139--145}}
@book{muitos, author={Ana Lima and Bia Reis and Caio Melo and Davi Nunes}, title={Título: subtítulo}, edition={3},
  publisher={Novatec}, address={São Paulo}, year={2015}}
@misc{site, author={{Ministério da Saúde}}, title={Meu SUS Digital}, year={2026},
  url={https://exemplo.gov.br/a%C3%A9b}, note={Acesso em: 2 jul. 2026}}
@phdthesis{tese, author={Rita Paz}, title={Uma tese}, school={UFPA}, address={Belém}, year={2020}}
"""


def abnt(key):
    return format_abnt(parse_bib(BIB)[key])


def test_abnt_references_follow_nbr_6023():
    assert abnt("evento") == ("OLIVEIRA, Denise; BORGES, José. Perspectivas digitais. In: I WORKSHOP DE INFORMÁTICA NA "
                              "EDUCAÇÃO INCLUSIVA, 2024, Rio de Janeiro. Anais [...]. Porto Alegre: SBC, 2024. p. 139–145.")
    assert abnt("muitos") == ("LIMA, Ana; REIS, Bia; MELO, Caio; NUNES, Davi. Título: subtítulo. 3. ed. "
                              "São Paulo: Novatec, 2015.")  # todos os autores, como recomenda a norma de 2018
    assert abnt("site") == ("MINISTÉRIO DA SAÚDE. Meu SUS Digital. 2026. Disponível em: https://exemplo.gov.br/a%C3%A9b. "
                            "Acesso em: 2 jul. 2026.")  # o % do endereço não some
    assert abnt("tese") == "PAZ, Rita. Uma tese. 2020. Tese (Doutorado) – UFPA, Belém, 2020."


def template_doc(template_id):
    template = next(t for t in TEMPLATES if t.id == template_id)
    doc = parse_document(template.build("T", "A")["main.tex"].decode())
    doc["citation_style"] = "abnt" if template_id == "abnt" else ""
    return doc


def test_each_template_gets_its_own_page():
    abnt_page = layout_for(template_doc("abnt"))
    assert (abnt_page.top, abnt_page.bottom, abnt_page.left, abnt_page.right) == (3 * cm, 2 * cm, 3 * cm, 2 * cm)
    assert (abnt_page.size, abnt_page.leading, abnt_page.indent) == (12, 18, 1.25 * cm)
    sbc = layout_for(template_doc("sbc"))
    assert (sbc.kind, sbc.top, sbc.left, sbc.indent) == ("sbc", 3.5 * cm, 3 * cm, 1.27 * cm)
    assert layout_for(template_doc("ieee")).columns == 2
    expanded = layout_for(template_doc("resumo-expandido"))  # \usepackage[margin=2.5cm]{geometry}
    assert (expanded.kind, expanded.left, expanded.top, expanded.size) == ("latex", 2.5 * cm, 2.5 * cm, 12)


def pdf_text(template_id):
    template = next(t for t in TEMPLATES if t.id == template_id)
    document = pdfium.PdfDocument(pdf_from_files(template.build("Meu artigo", "Ana Souza")))
    try:
        return "\n".join(document[i].get_textpage().get_text_range() for i in range(len(document)))
    finally:
        document.close()


@pytest.mark.parametrize("template_id, expected, absent", [
    ("abnt", ["RESUMO", "1 INTRODUÇÃO", "2 REFERENCIAL TEÓRICO", "REFERÊNCIAS"], ["1. Introdução"]),
    ("sbc", ["Abstract.", "Resumo.", "1. Introdução"], ["1 INTRODUÇÃO"]),
    ("ieee", ["Abstract—", "I. INTRODUCTION", "REFERENCES", "[1]"], ["1. Introduction"]),
])
def test_pdf_headings_follow_the_format(template_id, expected, absent):
    text = pdf_text(template_id).replace("\r", "")
    for piece in expected:
        assert piece in text
    for piece in absent:
        assert piece not in text


FIGURES = {
    "editor": "\\begin{figure}\n  \\caption{Tela}\n  \\includegraphics{a.png}\n  \\par\\small Fonte: Os autores (2026).\n\\end{figure}",
    "abntex2": "\\begin{figure}\n\\includegraphics{a.png}\n\\caption{Tela}\n\\fonte{Os autores (2026).}\n\\end{figure}",
    "legend": "\\begin{figure}\n\\includegraphics{a.png}\n\\legend{Fonte: Os autores (2026).}\n\\caption{Tela}\n\\end{figure}",
}


def figure_of(body):
    source = "\\documentclass{article}\n\\begin{document}\n\n" + body + "\n\n\\end{document}\n"
    doc = parse_document(source)
    return source, doc, next(b for b in doc["blocks"] if b["type"] == "figure")


@pytest.mark.parametrize("form", FIGURES)
def test_figure_source_is_read_edited_and_removed(form):
    source, doc, figure = figure_of(FIGURES[form])
    assert figure["source"] == [{"t": "Os autores (2026)."}]
    assert serialize_document(doc) == source  # sem editar, nada muda

    figure["source"] = [{"t": "IBGE (2022)"}]
    edited = serialize_document(doc)
    assert "IBGE (2022)" in edited and "Os autores" not in edited
    assert figure_of(edited.split("\n\n")[1])[2]["source"] == [{"t": "IBGE (2022)"}]

    figure["source"] = []
    removed = serialize_document(doc)
    assert "Os autores" not in removed and "Fonte" not in removed and "\n\n\\caption" not in removed


def test_figure_without_source_gets_one_line():
    _, doc, figure = figure_of("\\begin{figure}\n\\includegraphics{a.png}\n\\caption{Tela}\n\\end{figure}")
    assert figure["source"] is None
    figure["source"] = [{"t": "Os autores"}]
    assert "\\caption{Tela}\n  \\par\\small Fonte: Os autores\n\\end{figure}" in serialize_document(doc)


def test_pdf_shows_figure_source_below_the_image():
    from PIL import Image as PILImage
    picture = io.BytesIO()
    PILImage.new("RGB", (40, 30), "white").save(picture, "PNG")
    tex = ("\\documentclass[12pt]{article}\n\\usepackage[alf]{abntex2cite}\n\\begin{document}\n\n"
           + FIGURES["editor"] + "\n\n\\end{document}\n")
    document = pdfium.PdfDocument(pdf_from_files({"main.tex": tex.encode(), "a.png": picture.getvalue()}))
    text = document[0].get_textpage().get_text_range().replace("\r", "")
    document.close()
    assert text.index("Figura 1 – Tela") < text.index("Fonte: Os autores (2026).")
