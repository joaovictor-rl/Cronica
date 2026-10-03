import io
import json
import zipfile

from tests.conftest import signup

TEX = "\\documentclass{article}\\begin{document}Oi\\end{document}"


def test_signup_requires_accepting_the_privacy_policy(client):
    data = {"name": "Ana", "email": "ana@exemplo.com", "password": "senha-segura"}
    assert client.post("/auth/register", json=data).status_code == 422
    assert client.post("/auth/register", json={**data, "accept_privacy": False}).status_code == 422
    assert client.post("/auth/register", json={**data, "accept_privacy": True}).status_code == 201


def test_download_my_data(client):
    ana = signup(client)
    client.patch("/auth/me", headers=ana, json={"bio": "Pesquiso IHC."})
    client.post("/articles", json={"title": "Meu artigo", "template": "abnt"}, headers=ana)
    response = client.get("/auth/me/export", headers=ana)
    assert response.headers["content-type"] == "application/zip"
    files = zipfile.ZipFile(io.BytesIO(response.content))
    profile = json.loads(files.read("perfil.json"))
    assert (profile["email"], profile["bio"], profile["artigos"][0]["titulo"]) == ("ana@exemplo.com", "Pesquiso IHC.", "Meu artigo")
    assert any(name.endswith("/main.tex") for name in files.namelist())
    assert "password_hash" not in profile


def test_delete_my_account(client):
    ana, bia = signup(client), signup(client, "bia@exemplo.com")
    bia_code = client.get("/auth/me", headers=bia).json()["code"]
    mine = client.post("/articles", json={"title": "Da Ana", "template": "em-branco"}, headers=ana).json()
    theirs = client.post("/articles", json={"title": "Da Bia", "template": "em-branco"}, headers=bia).json()
    client.post(f"/articles/{theirs['id']}/invites", json={"code": client.get("/auth/me", headers=ana).json()["code"]}, headers=bia)
    for invite in client.get("/invites", headers=ana).json():
        client.post(f"/invites/{invite['id']}/accept", headers=ana)
    # A Ana salva uma versão no artigo da Bia antes de sair.
    client.post(f"/articles/{theirs['id']}/edits", headers=ana, json={"base_version": theirs["head"], "message": "Ajuste", "source": TEX})
    client.post(f"/articles/{mine['id']}/invites", json={"code": bia_code}, headers=ana)

    assert client.post("/auth/me/delete", headers=ana, json={"password": "errada"}).status_code == 403
    assert client.post("/auth/me/delete", headers=ana, json={"password": "senha-segura"}).status_code == 204

    assert client.get("/auth/me", headers=ana).status_code == 401
    assert client.post("/auth/login", data={"username": "ana@exemplo.com", "password": "senha-segura"}).status_code == 401
    assert [a["title"] for a in client.get("/articles", headers=bia).json()] == ["Da Bia"]
    assert client.get("/invites", headers=bia).json() == []
    # O histórico do artigo da Bia continua, com a autora anonimizada.
    versions = client.get(f"/articles/{theirs['id']}/versions", headers=bia).json()
    assert [v["author"]["name"] for v in versions] == ["Conta excluída", "Ana"]
    # O e-mail fica livre para uma conta nova.
    assert client.post("/auth/register", json={"name": "Ana", "email": "ana@exemplo.com", "password": "senha-segura", "accept_privacy": True}).status_code == 201
