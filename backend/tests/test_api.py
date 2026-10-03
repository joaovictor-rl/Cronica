from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Blob
from tests.conftest import send, signup

V1 = {
    "main.tex": "\\section{Intro}\nO método foi testado em 30 gravações. Os resultados são bons.\n",
    "refs.bib": "@article{silva2020, title={Música}, year={2020}}",
    "figs/grafico.png": b"\x89PNG\r\n\x1a\nfake-image",
    "main.aux": "lixo gerado",
}


def new_article(client, headers):
    return client.post("/articles", json={"title": "Música na Amazônia"}, headers=headers).json()


def test_requires_login(client):
    assert client.get("/articles").status_code == 401


def test_register_rejects_duplicate_email(client):
    signup(client)
    response = client.post("/auth/register", json={"name": "A", "email": "ANA@exemplo.com", "password": "outra-senha", "accept_privacy": True})
    assert response.status_code == 409


def test_create_article_starts_without_versions(client):
    headers = signup(client)
    article = new_article(client, headers)
    assert (article["head"], article["versions"]) == (None, 0)


def test_first_commit_stores_tree_without_generated_files(client):
    headers = signup(client)
    article = new_article(client, headers)
    version = send(client, headers, article["id"], V1, "primeira versão")
    assert version.status_code == 201, version.text
    assert len(version.json()["hash"]) == 64

    detail = client.get(f"/articles/{article['id']}/versions/{version.json()['hash'][:8]}", headers=headers).json()
    assert [f["path"] for f in detail["files"]] == ["figs/grafico.png", "main.tex", "refs.bib"]
    assert {f["path"]: f["is_text"] for f in detail["files"]}["figs/grafico.png"] is False


def test_commit_flow_history_and_diff(client):
    headers = signup(client)
    article_id = new_article(client, headers)["id"]
    v1 = send(client, headers, article_id, V1).json()["hash"]

    v2_files = {**V1, "main.tex": V1["main.tex"].replace("30", "45")}
    v2_files["figuras/grafico.png"] = v2_files.pop("figs/grafico.png")
    v2_files["refs.bib"] = V1["refs.bib"].replace("2020}}", "2021}}")
    v2 = send(client, headers, article_id, v2_files, "mais gravações", base=v1).json()["hash"]

    log = client.get(f"/articles/{article_id}/versions", headers=headers).json()
    assert [v["hash"] for v in log] == [v2, v1]
    assert log[0]["parent_hash"] == v1

    diff = client.get(f"/articles/{article_id}/diff", params={"to": v2}, headers=headers).json()
    assert diff["from_version"] == v1
    files = {f["path"]: f for f in diff["files"]}
    assert files["figuras/grafico.png"] == {"path": "figuras/grafico.png", "old_path": "figs/grafico.png", "status": "renamed"}
    assert files["main.tex"]["diff"]["stats"]["modified"] == 1
    assert files["refs.bib"]["diff"]["changes"][0]["fields"] == {"year": {"old": "2020", "new": "2021"}}


def test_identical_files_are_stored_once(client):
    headers = signup(client)
    a1 = new_article(client, headers)["id"]
    a2 = new_article(client, headers)["id"]
    v1 = send(client, headers, a1, V1).json()["hash"]
    send(client, headers, a1, {**V1, "main.tex": "Outro texto."}, base=v1)
    send(client, headers, a2, V1)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Blob)) == 4


def test_stale_base_returns_conflict(client):
    headers = signup(client)
    article_id = new_article(client, headers)["id"]
    v1 = send(client, headers, article_id, V1).json()["hash"]
    v2 = send(client, headers, article_id, {**V1, "main.tex": "Versão 2."}, base=v1).json()["hash"]

    stale = send(client, headers, article_id, {**V1, "main.tex": "Versão paralela."}, base=v1)
    assert stale.status_code == 409
    assert stale.json()["detail"]["current_head"] == v2

    missing_base = send(client, headers, article_id, {**V1, "main.tex": "Sem base."})
    assert missing_base.status_code == 409


def test_commit_without_changes_is_rejected(client):
    headers = signup(client)
    article_id = new_article(client, headers)["id"]
    v1 = send(client, headers, article_id, V1).json()["hash"]
    response = send(client, headers, article_id, {**V1, "main.log": "só lixo novo"}, base=v1)
    assert response.status_code == 422


def test_malicious_zip_is_rejected(client):
    headers = signup(client)
    article_id = new_article(client, headers)["id"]
    response = send(client, headers, article_id, {"main.tex": "ok", "../../etc/x": "x"})
    assert response.status_code == 422
    assert "local não permitido" in response.json()["detail"]


def test_read_file_content(client):
    headers = signup(client)
    article_id = new_article(client, headers)["id"]
    v1 = send(client, headers, article_id, V1).json()["hash"]
    response = client.get(f"/articles/{article_id}/versions/{v1}/files/main.tex", headers=headers)
    assert response.text == V1["main.tex"]
    missing = client.get(f"/articles/{article_id}/versions/{v1}/files/nao-existe.tex", headers=headers)
    assert missing.status_code == 404


def test_other_users_cannot_see_article(client):
    owner = signup(client)
    article_id = new_article(client, owner)["id"]
    v1 = send(client, owner, article_id, V1).json()["hash"]

    intruder = signup(client, "bruno@exemplo.com")
    assert client.get(f"/articles/{article_id}", headers=intruder).status_code == 404
    assert client.get(f"/articles/{article_id}/versions/{v1}/files/main.tex", headers=intruder).status_code == 404
    assert send(client, intruder, article_id, V1, base=v1).status_code == 404


def test_version_of_another_article_is_not_found(client):
    headers = signup(client)
    a1 = new_article(client, headers)["id"]
    a2 = new_article(client, headers)["id"]
    v1 = send(client, headers, a1, V1).json()["hash"]
    assert client.get(f"/articles/{a2}/versions/{v1}", headers=headers).status_code == 404


def test_first_version_diff_needs_from(client):
    headers = signup(client)
    article_id = new_article(client, headers)["id"]
    v1 = send(client, headers, article_id, V1).json()["hash"]
    assert client.get(f"/articles/{article_id}/diff", params={"to": v1}, headers=headers).status_code == 400


def test_same_content_in_two_paths_of_one_zip(client):
    headers = signup(client)
    article_id = new_article(client, headers)["id"]
    response = send(client, headers, article_id, {"a.tex": "igual", "copia/a.tex": "igual"})
    assert response.status_code == 201
