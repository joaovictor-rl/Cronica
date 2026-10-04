import io

import pytest
from PIL import Image

from app.document.blocks import parse_document, serialize_document
from app.document.templates import TEMPLATES
from tests.conftest import signup


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.id)
def test_template_is_a_clean_latex_project(template):
    files = template.build("Título com 100% & #1", "Ana Souza")
    source = files["main.tex"].decode()
    assert "Título com 100\\% \\& \\#1" in source
    doc = parse_document(source)
    assert serialize_document(doc) == source  # salvar sem editar não muda nada
    assert not [b for b in doc["blocks"] if b["type"] == "raw"]  # o editor mostra tudo, sem código solto
    if "\\bibliography{" in source:
        bib = source.split("\\bibliography{")[1].split("}")[0]
        assert f"{bib}.bib" in files


def test_list_templates_with_sections(client):
    found = {t["id"]: t for t in client.get("/templates").json()}
    assert list(found) == [t.id for t in TEMPLATES]
    assert found["sbc"]["sections"][:2] == ["Introdução", "Trabalhos Relacionados"]
    assert found["ieee"]["language"] == "en"


def test_template_preview_is_an_image(client):
    response = client.get("/templates/abnt/preview.png")
    assert response.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(response.content)).width > 300
    assert client.get("/templates/nao-existe/preview.png").status_code == 404


def test_create_article_from_a_template(client):
    headers = signup(client)
    article = client.post("/articles", json={"title": "Meu artigo", "template": "sbc"}, headers=headers).json()
    head = article["head"]
    files = {f["path"] for f in client.get(f"/articles/{article['id']}/versions/{head}", headers=headers).json()["files"]}
    assert files == {"main.tex", "referencias.bib", "sbc-template.sty", "sbc.bst"}
    doc = client.get(f"/articles/{article['id']}/versions/{head}/document", headers=headers).json()
    labels = [s.get("label") for b in doc["blocks"] if b["type"] == "paragraph" for s in b["spans"] if s.get("kind") == "cite"]
    assert labels == ["[Barbosa and da Silva 2010]"]
    assert client.get(f"/articles/{article['id']}/versions/{head}/pdf", headers=headers).status_code == 200
    versions = client.get(f"/articles/{article['id']}/versions", headers=headers).json()
    assert versions[0]["message"] == "Artigo criado a partir do modelo Artigo SBC"


def test_unknown_template_is_refused(client):
    headers = signup(client)
    assert client.post("/articles", json={"title": "X", "template": "abc"}, headers=headers).status_code == 422
    assert client.get("/articles", headers=headers).json() == []


def cite_labels(doc):
    return [s["label"] for b in doc["blocks"] if b["type"] == "paragraph" for s in b["spans"] if s.get("kind") == "cite"]


def annotated(source, bib):
    from app.document.references import annotate, parse_bib
    return annotate(parse_document(source), parse_bib(bib))


BIB = """@book{zeta, author={Ana Zeta}, title={Z}, year={2020}, publisher={P}}
@article{alfa, author={Bruno Alfa and Carla da Costa}, title={A}, journal={Revista}, volume={3}, pages={1--9}, year={2019}}"""


def test_numbered_citations_follow_the_order_in_the_text():
    source = "\\documentclass{article}\\begin{document}Um \\cite{zeta}, dois \\cite{alfa,zeta}.\n\n\\bibliographystyle{IEEEtran}\n\\bibliography{r}\n\\end{document}"
    doc = annotated(source, BIB)
    assert cite_labels(doc) == ["[1]", "[2, 1]"]
    assert [e["number"] for e in doc["bibliography"]] == [1, 2]
    assert doc["bibliography"][1]["text"] == "B. Alfa and C. da Costa, “A,” Revista, vol. 3, pp. 1–9, 2019."
    assert doc["references_title"] == "References"


def test_abnt_citations_and_references():
    source = ("\\documentclass{article}\\usepackage[brazil]{babel}\\usepackage[alf]{abntex2cite}\\begin{document}"
              "Segundo \\citeonline{alfa}, isso vale \\cite{zeta}.\n\n\\bibliography{r}\n\\end{document}")
    doc = annotated(source, BIB)
    assert cite_labels(doc) == ["Alfa e Costa (2019)", "(ZETA, 2020)"]
    assert [e["text"] for e in doc["bibliography"]] == [
        "ALFA, Bruno; COSTA, Carla da. A. Revista, v. 3, p. 1–9, 2019.",
        "ZETA, Ana. Z. [S. l.]: P, 2020.",
    ]
    assert [e["emphasis"] for e in doc["bibliography"]] == ["Revista", "Z"]
    assert doc["references_title"] == "Referências"


def test_previews_in_parallel_do_not_crash(client):
    """O navegador pede as prévias todas ao mesmo tempo; o pdfium precisa ser usado uma thread por vez."""
    from concurrent.futures import ThreadPoolExecutor

    from app.routers.templates import preview_png
    preview_png.cache_clear()
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda t: client.get(f"/templates/{t.id}/preview.png").status_code, TEMPLATES * 3))
    assert set(results) == {200}
