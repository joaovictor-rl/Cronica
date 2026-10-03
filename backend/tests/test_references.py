import httpx

from app.document.bibtex import chunks, make_key, write_bib
from tests.conftest import signup

ORIGINAL = """% Referências do grupo
@string{ihc = "Simpósio de IHC"}

@book{barbosa2010ihc,
    author = {Simone Barbosa   and Bruno da Silva},
    title  = {Interação Humano-Computador},
    year   = 2010
}

@article{velho2020,
  author = {Ana Velho}, title = {Antigo}, journal = {Revista}, year = {2020}}
"""


def test_unchanged_references_are_written_exactly_as_before():
    entries = [{"key": c["key"], "type": c["type"], "fields": c["fields"]} for c in chunks(ORIGINAL) if "key" in c]
    text = write_bib(ORIGINAL, entries)
    assert "@book{barbosa2010ihc,\n    author = {Simone Barbosa   and Bruno da Silva}," in text
    assert "% Referências do grupo" in text and '@string{ihc = "Simpósio de IHC"}' in text


def test_changed_added_and_removed_references():
    entries = [c for c in chunks(ORIGINAL) if "key" in c]
    book = {"key": "barbosa2010ihc", "type": "book", "fields": {**entries[0]["fields"], "publisher": "Elsevier"}}
    new = {"key": "nova2024", "type": "misc", "fields": {"title": "Site {com chave", "url": "https://exemplo.com", "year": "2024"}}
    text = write_bib(ORIGINAL, [book, new])
    assert "velho2020" not in text
    assert "  publisher = {Elsevier}," in text
    assert "  title = {Site com chave}," in text  # chave sem par não quebra o arquivo
    assert [c["key"] for c in chunks(text) if "key" in c] == ["barbosa2010ihc", "nova2024"]


def test_readable_unique_keys():
    fields = {"author": "Bruno Santana da Silva and Ana Souza", "title": "A Interação no Celular", "year": "2021"}
    assert make_key(fields, set()) == "silva2021interacao"
    assert make_key(fields, {"silva2021interacao"}) == "silva2021interacaob"
    assert make_key({"title": "Só título"}, set()) == "refso"


def article(client, headers, template="em-branco"):
    created = client.post("/articles", json={"title": "Com referências", "template": template}, headers=headers).json()
    return created["id"], created["head"]


def test_add_references_and_cite_them_while_editing(client):
    headers = signup(client)
    aid, head = article(client, headers)
    listed = client.get(f"/articles/{aid}/versions/{head}/references", headers=headers).json()
    assert listed["entries"] == [] and listed["path"] == "referencias.bib"

    entry = client.post("/references/check", headers=headers, json={"entry": {
        "type": "book", "fields": {"author": "Donald A. Norman", "title": "The Design of Everyday Things",
                                   "year": "2013", "publisher": "Basic Books"}}}).json()
    assert entry["key"] == "norman2013design" and entry["label"] == "[Norman 2013]"

    doc = client.get(f"/articles/{aid}/versions/{head}/document", headers=headers).json()
    paragraph = next(b for b in doc["blocks"] if b["type"] == "paragraph")
    paragraph["spans"] = [{"t": "Como mostra "}, {"raw": "\\cite{norman2013design}", "kind": "cite", "keys": ["norman2013design"], "label": ""}, {"t": "."}]
    refs = [{"key": entry["key"], "type": entry["type"], "fields": entry["fields"]}]

    preview = client.post(f"/articles/{aid}/preview", headers=headers, json={"base_version": head, "document": doc, "references": refs})
    assert preview.status_code == 200 and preview.json()["pages"][0].startswith("data:image/png;base64,")

    saved = client.post(f"/articles/{aid}/edits", headers=headers, json={
        "base_version": head, "message": "Referência nova", "document": doc, "references": refs}).json()
    files = {f["path"] for f in client.get(f"/articles/{aid}/versions/{saved['hash']}", headers=headers).json()["files"]}
    assert files == {"main.tex", "referencias.bib"}
    source = client.get(f"/articles/{aid}/versions/{saved['hash']}/files/main.tex", headers=headers).text
    assert "\\bibliographystyle{plain}\n\\bibliography{referencias}" in source
    listed = client.get(f"/articles/{aid}/versions/{saved['hash']}/references", headers=headers).json()
    assert [(e["key"], e["cited"], e["label"]) for e in listed["entries"]] == [("norman2013design", 1, "[1]")]

    diff = client.get(f"/articles/{aid}/diff?to={saved['hash']}", headers=headers).json()
    assert {f["path"] for f in diff["files"]} == {"main.tex", "referencias.bib"}


def test_saving_without_touching_references_keeps_the_bib(client):
    headers = signup(client)
    aid, head = article(client, headers, "sbc")
    doc = client.get(f"/articles/{aid}/versions/{head}/document", headers=headers).json()
    doc["blocks"][3]["spans"] = [{"t": "Introdução nova."}]
    saved = client.post(f"/articles/{aid}/edits", headers=headers, json={"base_version": head, "message": "x", "document": doc}).json()
    diff = client.get(f"/articles/{aid}/diff?to={saved['hash']}", headers=headers).json()
    assert [f["path"] for f in diff["files"]] == ["main.tex"]


def test_paste_bibtex_from_google_scholar(client):
    headers = signup(client)
    pasted = "@inproceedings{silva2021,\n title={Acessibilidade},\n author={Silva, Ana},\n booktitle={Anais do IHC},\n year={2021}\n}"
    found = client.post("/references/parse", headers=headers, json={"bibtex": pasted, "taken": ["silva2021"], "style": "abnt"}).json()
    assert [(e["key"], e["label"]) for e in found] == [("silva2021acessibilida", "(SILVA, 2021)")]
    assert client.post("/references/parse", headers=headers, json={"bibtex": "só texto"}).status_code == 422


def test_find_by_doi(client, monkeypatch):
    import app.routers.references as refs
    answer = "@article{Norman_2013, title={Design}, author={Norman, Donald}, journal={Revista}, year={2013}, month=jan}"
    monkeypatch.setattr(refs, "fetch_bibtex", lambda doi: answer)
    headers = signup(client)
    found = client.get("/references/doi", headers=headers, params={"doi": "https://doi.org/10.1145/123.456"}).json()
    assert found["key"] == "Norman_2013" and found["fields"]["doi"] == "10.1145/123.456"
    assert client.get("/references/doi", headers=headers, params={"doi": "não é doi"}).status_code == 422

    def offline(doi):
        raise httpx.ConnectError("sem rede")
    monkeypatch.setattr(refs, "fetch_bibtex", offline)
    assert client.get("/references/doi", headers=headers, params={"doi": "10.1145/1"}).status_code == 502


def test_pages_show_the_same_pdf(client):
    headers = signup(client)
    aid, head = article(client, headers, "sbc")
    count = client.get(f"/articles/{aid}/versions/{head}/pages", headers=headers).json()
    assert count["pages"] >= 1
    page = client.get(f"/articles/{aid}/versions/{head}/pages/1.png", headers=headers)
    assert page.headers["content-type"] == "image/png"
    assert client.get(f"/articles/{aid}/versions/{head}/pages/99.png", headers=headers).status_code == 404
    intruder = signup(client, "bia@exemplo.com")
    assert client.get(f"/articles/{aid}/versions/{head}/pages/1.png", headers=intruder).status_code == 404


def test_add_an_image_as_a_new_figure(client):
    import base64
    import io

    from PIL import Image

    headers = signup(client)
    aid, head = article(client, headers)
    buffer = io.BytesIO()
    Image.new("RGB", (300, 200), "blue").save(buffer, "WEBP")  # formato que o LaTeX não lê: vira PNG
    data = base64.b64encode(buffer.getvalue()).decode()
    doc = client.get(f"/articles/{aid}/versions/{head}/document", headers=headers).json()
    src = "\\begin{figure}[htbp]\n  \\centering\n  \\includegraphics[width=0.8\\textwidth]{imagens/grafico.png}\n  \\caption{Legenda}\n  \\label{fig:grafico}\n\\end{figure}"
    start = src.index("\\caption{") + 9
    doc["blocks"].append({"type": "figure", "src": src, "images": [{"path": "imagens/grafico.png", "caption": None}],
                          "caption": [{"t": "Resultado do teste"}], "cap": [start, start + 7], "label": "fig:grafico"})
    body = {"base_version": head, "message": "Figura", "document": doc, "images": [{"path": "imagens/grafico.png", "data": data}]}
    saved = client.post(f"/articles/{aid}/edits", headers=headers, json=body).json()
    image = client.get(f"/articles/{aid}/versions/{saved['hash']}/images/imagens/grafico.png", headers=headers)
    assert image.headers["content-type"] == "image/png"
    source = client.get(f"/articles/{aid}/versions/{saved['hash']}/files/main.tex", headers=headers).text
    assert "\\caption{Resultado do teste}" in source

    bad = {**body, "base_version": saved["hash"], "images": [{"path": "../main.tex", "data": data}]}
    assert client.post(f"/articles/{aid}/edits", headers=headers, json=bad).status_code == 422
    fake = {**body, "base_version": saved["hash"], "images": [{"path": "imagens/x.png", "data": base64.b64encode(b"oi").decode()}]}
    assert client.post(f"/articles/{aid}/edits", headers=headers, json=fake).status_code == 422
    again = {**body, "base_version": saved["hash"]}
    assert client.post(f"/articles/{aid}/edits", headers=headers, json=again).status_code == 409
