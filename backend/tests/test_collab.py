import io

from PIL import Image

from tests.conftest import signup

TEX = "\\documentclass{article}\\begin{document}Oi\\end{document}"


def me(client, headers):
    return client.get("/auth/me", headers=headers).json()


def accept_all(client, headers):
    for invite in client.get("/invites", headers=headers).json():
        assert client.post(f"/invites/{invite['id']}/accept", headers=headers).status_code == 204


def image_bytes(size=(800, 400), mode="RGB", fmt="PNG"):
    buffer = io.BytesIO()
    Image.new(mode, size, "red").save(buffer, fmt)
    return buffer.getvalue()


def test_every_user_gets_a_personal_code(client):
    a, b = me(client, signup(client)), me(client, signup(client, "bia@exemplo.com"))
    assert a["code"] != b["code"]
    assert len(a["code"]) == 9 and a["code"][4] == "-"


def test_find_by_code_accepts_lowercase_and_no_dash(client):
    ana = signup(client)
    bia = me(client, signup(client, "bia@exemplo.com"))
    loose = bia["code"].replace("-", "").lower()
    found = client.get(f"/users/by-code/{loose}", headers=ana).json()
    assert found == {"id": bia["id"], "name": "Ana", "institution": "", "picture_at": None}
    assert "email" not in found
    assert client.get("/users/by-code/ZZZZ-ZZZZ", headers=ana).status_code == 404


def test_invite_coauthor_flow(client):
    ana, bia = signup(client), signup(client, "bia@exemplo.com")
    code = me(client, bia)["code"]
    article = client.post("/articles", json={"title": "Juntos", "template": "em-branco"}, headers=ana).json()
    aid = article["id"]

    # Antes de aceitar, a convidada não vê o artigo.
    assert client.post(f"/articles/{aid}/invites", json={"code": code}, headers=ana).status_code == 201
    assert client.get(f"/articles/{aid}", headers=bia).status_code == 404
    assert client.post(f"/articles/{aid}/invites", json={"code": code}, headers=ana).status_code == 409

    [invite] = client.get("/invites", headers=bia).json()
    assert (invite["kind"], invite["target_name"]) == ("artigo", "Juntos")
    people = client.get(f"/articles/{aid}/members", headers=ana).json()
    assert len(people["pending"]) == 1

    accept_all(client, bia)
    assert client.get("/invites", headers=bia).json() == []
    seen = client.get(f"/articles/{aid}", headers=bia).json()
    assert seen["role"] == "coautor"
    assert [a["id"] for a in client.get("/articles", headers=bia).json()] == [aid]

    # A coautora edita e salva uma versão.
    head = seen["head"]
    saved = client.post(f"/articles/{aid}/edits", headers=bia, json={"base_version": head, "message": "Revisão", "source": TEX})
    assert saved.status_code == 201
    assert "email" not in saved.json()["author"]
    assert me(client, bia)["versions"] == 1 and me(client, bia)["articles"] == 1

    people = client.get(f"/articles/{aid}/members", headers=bia).json()
    assert [m["role"] for m in people["members"]] == ["dono", "coautor"] and people["pending"] == []

    # Só o dono convida e muda a organização.
    other = me(client, signup(client, "caio@exemplo.com"))["code"]
    assert client.post(f"/articles/{aid}/invites", json={"code": other}, headers=bia).status_code == 403
    assert client.post(f"/articles/{aid}/invites", json={"code": me(client, ana)["code"]}, headers=ana).status_code == 422


def test_coauthor_leaves_and_owner_removes(client):
    ana, bia = signup(client), signup(client, "bia@exemplo.com")
    bia_me = me(client, bia)
    aid = client.post("/articles", json={"title": "X"}, headers=ana).json()["id"]
    client.post(f"/articles/{aid}/invites", json={"code": bia_me["code"]}, headers=ana)
    accept_all(client, bia)

    ana_id = me(client, ana)["id"]
    assert client.delete(f"/articles/{aid}/members/{ana_id}", headers=bia).status_code == 403
    assert client.delete(f"/articles/{aid}/members/{ana_id}", headers=ana).status_code == 422
    assert client.delete(f"/articles/{aid}/members/{bia_me['id']}", headers=bia).status_code == 204
    assert client.get(f"/articles/{aid}", headers=bia).status_code == 404


def test_decline_and_cancel_invite(client):
    ana, bia = signup(client), signup(client, "bia@exemplo.com")
    code = me(client, bia)["code"]
    aid = client.post("/articles", json={"title": "X"}, headers=ana).json()["id"]

    invite = client.post(f"/articles/{aid}/invites", json={"code": code}, headers=ana).json()
    assert client.post(f"/invites/{invite['id']}/accept", headers=ana).status_code == 404  # não é para ela
    assert client.post(f"/invites/{invite['id']}/decline", headers=bia).status_code == 204
    assert client.get(f"/articles/{aid}", headers=bia).status_code == 404

    invite = client.post(f"/articles/{aid}/invites", json={"code": code}, headers=ana).json()
    assert client.delete(f"/articles/{aid}/invites/{invite['id']}", headers=ana).status_code == 204
    assert client.get("/invites", headers=bia).json() == []


def test_organization_shares_its_articles(client):
    ana, bia = signup(client), signup(client, "bia@exemplo.com")
    org = client.post("/orgs", json={"name": "Grupo de IHC", "description": "UFPA"}, headers=ana).json()
    assert (org["members"], org["is_owner"]) == (1, True)

    article = client.post("/articles", json={"title": "Do grupo", "org_id": org["id"]}, headers=ana).json()
    assert article["org_name"] == "Grupo de IHC"
    assert client.get(f"/orgs/{org['id']}", headers=bia).status_code == 404

    client.post(f"/orgs/{org['id']}/invites", json={"code": me(client, bia)["code"]}, headers=ana)
    [invite] = client.get("/invites", headers=bia).json()
    assert invite["target_name"] == "Grupo de IHC"
    accept_all(client, bia)

    assert client.get(f"/articles/{article['id']}", headers=bia).json()["role"] == "organizacao"
    assert [a["title"] for a in client.get(f"/orgs/{org['id']}/articles", headers=bia).json()] == ["Do grupo"]
    assert [m["role"] for m in client.get(f"/orgs/{org['id']}/members", headers=bia).json()["members"]] == ["dono", "membro"]
    assert client.patch(f"/orgs/{org['id']}", json={"name": "Outro"}, headers=bia).status_code == 403

    # A membro cria um artigo dentro da organização; quem não é membro não pode.
    assert client.post("/articles", json={"title": "Meu", "org_id": org["id"]}, headers=bia).status_code == 201
    caio = signup(client, "caio@exemplo.com")
    assert client.post("/articles", json={"title": "Intruso", "org_id": org["id"]}, headers=caio).status_code == 404

    # Tirar o artigo da organização corta o acesso de quem só entrava por ela.
    assert client.patch(f"/articles/{article['id']}", json={"org_id": None}, headers=ana).json()["org_id"] is None
    assert client.get(f"/articles/{article['id']}", headers=bia).status_code == 404


def test_delete_organization_keeps_articles(client):
    ana = signup(client)
    org = client.post("/orgs", json={"name": "G"}, headers=ana).json()
    aid = client.post("/articles", json={"title": "A", "org_id": org["id"]}, headers=ana).json()["id"]
    assert client.delete(f"/orgs/{org['id']}", headers=ana).status_code == 204
    assert client.get(f"/articles/{aid}", headers=ana).json()["org_id"] is None
    assert client.get("/orgs", headers=ana).json() == []


def test_profile_picture_is_squared_and_reencoded(client):
    ana = signup(client)
    response = client.post("/auth/me/picture", headers=ana, files={"file": ("foto.png", image_bytes(), "image/png")})
    assert response.status_code == 200 and response.json()["picture_at"]
    picture = client.get(f"/users/{me(client, ana)['id']}/picture", headers=ana)
    assert picture.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(picture.content)).size == (256, 256)

    assert client.delete("/auth/me/picture", headers=ana).json()["picture_at"] is None
    assert client.get(f"/users/{me(client, ana)['id']}/picture", headers=ana).status_code == 404


def test_picture_rejects_non_images(client):
    ana = signup(client)
    bad = client.post("/auth/me/picture", headers=ana, files={"file": ("x.png", b"<script>", "image/png")})
    assert bad.status_code == 422
    transparent = image_bytes((300, 300), "RGBA")
    assert client.post("/auth/me/picture", headers=ana, files={"file": ("t.png", transparent, "image/png")}).status_code == 200


def test_org_picture_only_by_owner(client):
    ana, bia = signup(client), signup(client, "bia@exemplo.com")
    org = client.post("/orgs", json={"name": "G"}, headers=ana).json()
    client.post(f"/orgs/{org['id']}/invites", json={"code": me(client, bia)["code"]}, headers=ana)
    accept_all(client, bia)
    upload = {"file": ("g.jpg", image_bytes(fmt="JPEG"), "image/jpeg")}
    assert client.post(f"/orgs/{org['id']}/picture", headers=bia, files=upload).status_code == 403
    assert client.post(f"/orgs/{org['id']}/picture", headers=ana, files=upload).json()["picture_at"]
    assert client.get(f"/orgs/{org['id']}/picture", headers=bia).status_code == 200


def test_profile_visible_only_to_people_you_work_with(client):
    ana, bia, caio = signup(client), signup(client, "bia@exemplo.com"), signup(client, "caio@exemplo.com")
    bia_id = me(client, bia)["id"]
    client.patch("/auth/me", headers=bia, json={"status": "Oi!", "interests": ["IHC"], "theme": "verde"})
    assert client.get(f"/users/{bia_id}", headers=ana).status_code == 404

    aid = client.post("/articles", json={"title": "Juntos"}, headers=ana).json()["id"]
    client.post(f"/articles/{aid}/invites", json={"code": me(client, bia)["code"]}, headers=ana)
    pending = client.get(f"/users/{bia_id}", headers=ana)  # com convite pendente já dá para ver quem é
    assert pending.status_code == 200 and pending.json()["shared_articles"] == []
    accept_all(client, bia)

    profile = client.get(f"/users/{bia_id}", headers=ana).json()
    assert (profile["status"], profile["interests"], profile["theme"]) == ("Oi!", ["IHC"], "verde")
    assert profile["shared_articles"] == [{"id": aid, "title": "Juntos"}]
    assert "email" not in profile and "code" not in profile
    assert client.get(f"/users/{bia_id}", headers=caio).status_code == 404
