import io
import zipfile

from tests.conftest import make_zip, signup
from tests.test_document import SMALL

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
       b"\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82")
PROJECT = {
    "main.tex": SMALL,
    "refs.bib": "@article{silva2020, author={Silva, Ana}, title={Um estudo}, journal={Revista}, year={2020}}",
    "img/a.png": PNG,
}


def import_project(client, headers, files=PROJECT):
    response = client.post("/articles/import", headers=headers,
                           files={"file": ("meu-artigo.zip", make_zip(files), "application/zip")})
    assert response.status_code == 201, response.text
    return response.json()


def head(article):
    return article["head"]


def test_new_article_starts_from_template(client):
    headers = signup(client)
    article = client.post("/articles", json={"title": "Meu artigo 100%", "template": "em-branco"}, headers=headers).json()
    doc = client.get(f"/articles/{article['id']}/versions/{head(article)}/document", headers=headers).json()
    assert doc["meta"]["title"]["spans"] == [{"t": "Meu artigo 100%"}]
    assert doc["meta"]["author"]["spans"] == [{"t": "Ana"}]
    assert [b["type"] for b in doc["blocks"] if b["type"] != "hidden"] == ["abstract", "heading", "paragraph"]


def test_import_uses_title_from_latex(client):
    headers = signup(client)
    article = import_project(client, headers)
    assert article["title"] == "Um título com itálico"
    assert head(article)


def test_document_has_numbers_and_citations(client):
    headers = signup(client)
    article = import_project(client, headers)
    doc = client.get(f"/articles/{article['id']}/versions/{head(article)}/document", headers=headers).json()
    assert doc["main"] == "main.tex"
    figure = next(b for b in doc["blocks"] if b["type"] == "figure")
    assert figure["number"] == "1"
    assert doc["bibliography"][0]["text"].startswith("Silva, A. (2020). Um estudo. Revista.")


def test_edit_creates_new_version_with_only_the_change(client):
    headers = signup(client)
    article = import_project(client, headers)
    base = head(article)
    doc = client.get(f"/articles/{article['id']}/versions/{base}/document", headers=headers).json()
    paragraph = next(b for b in doc["blocks"] if b["type"] == "paragraph")
    paragraph["spans"][0]["t"] = paragraph["spans"][0]["t"].replace("50%", "75%")

    saved = client.post(f"/articles/{article['id']}/edits", headers=headers,
                        json={"base_version": base, "message": "Atualiza porcentagem", "document": doc})
    assert saved.status_code == 201, saved.text
    assert saved.json()["parent_hash"] == base

    diff = client.get(f"/articles/{article['id']}/diff", params={"to": saved.json()["hash"]}, headers=headers).json()
    [file] = diff["files"]
    assert file["path"] == "main.tex" and file["diff"]["stats"]["modified"] == 1

    content = client.get(f"/articles/{article['id']}/versions/{saved.json()['hash']}/files/main.tex", headers=headers).text
    assert "75\\%" in content and "\\includegraphics" in content


def test_edit_on_old_version_is_a_conflict(client):
    headers = signup(client)
    article = import_project(client, headers)
    base = head(article)
    source = client.get(f"/articles/{article['id']}/versions/{base}/files/main.tex", headers=headers).text
    first = client.post(f"/articles/{article['id']}/edits", headers=headers,
                        json={"base_version": base, "message": "Primeira", "source": source.replace("antiga", "nova")})
    assert first.status_code == 201
    second = client.post(f"/articles/{article['id']}/edits", headers=headers,
                         json={"base_version": base, "message": "Paralela", "source": source + "% x"})
    assert second.status_code == 409
    assert second.json()["detail"]["current_head"] == first.json()["hash"]


def test_pdf_zip_and_images(client):
    headers = signup(client)
    article = import_project(client, headers)
    base = head(article)
    pdf = client.get(f"/articles/{article['id']}/versions/{base}/pdf", headers=headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert "attachment" in pdf.headers["content-disposition"]

    archive = client.get(f"/articles/{article['id']}/versions/{base}/zip", headers=headers)
    assert sorted(zipfile.ZipFile(io.BytesIO(archive.content)).namelist()) == sorted(PROJECT)

    image = client.get(f"/articles/{article['id']}/versions/{base}/images/img/a", headers=headers)
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    missing = client.get(f"/articles/{article['id']}/versions/{base}/images/nada.png", headers=headers)
    assert missing.status_code == 404


def test_other_users_cannot_read_documents(client):
    article = import_project(client, signup(client))
    intruder = signup(client, "bruno@exemplo.com")
    for path in ("document", "pdf", "zip", "images/img/a.png"):
        assert client.get(f"/articles/{article['id']}/versions/{head(article)}/{path}", headers=intruder).status_code == 404
