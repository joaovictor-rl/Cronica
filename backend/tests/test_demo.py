from datetime import timedelta

from sqlalchemy import func, select

from app import demo
from app.database import SessionLocal
from app.models import Blob, User, Version, now
from tests.conftest import signup


def start(client):
    token = client.post("/auth/demo").json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_demo_has_the_real_article_in_four_versions(client):
    demo = start(client)
    me = client.get("/auth/me", headers=demo).json()
    assert me["is_demo"] and me["expires_at"]
    [article] = client.get("/articles", headers=demo).json()
    versions = client.get(f"/articles/{article['id']}/versions", headers=demo).json()
    assert len(versions) == 4
    assert versions[2]["author"]["name"] == "Colega de grupo"
    doc = client.get(f"/articles/{article['id']}/versions/{versions[0]['hash']}/document", headers=demo).json()
    assert not any(b["type"] == "raw" and "abstractp" in b["src"] for b in doc["blocks"])
    assert len(client.get("/invites", headers=demo).json()) == 1


def test_each_visitor_gets_a_separate_copy(client):
    ana, bia = start(client), start(client)
    [article] = client.get("/articles", headers=ana).json()
    client.patch("/auth/me", headers=ana, json={"name": "Mudei o nome"})
    head = article["head"]
    client.post(f"/articles/{article['id']}/edits", headers=ana,
                json={"base_version": head, "message": "teste", "source": "\\documentclass{article}\\begin{document}x\\end{document}"})

    assert client.get(f"/articles/{article['id']}", headers=bia).status_code == 404
    [other] = client.get("/articles", headers=bia).json()
    assert other["id"] != article["id"] and other["versions"] == 4
    assert client.get("/auth/me", headers=bia).json()["name"] == "Conta de demonstração"

    # As figuras ficam uma vez só no banco, por mais cópias que existam.
    with SessionLocal() as db:
        blobs = db.scalar(select(func.count()).select_from(Blob))
    start(client)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Blob)) == blobs


def test_switch_to_the_colleague_and_back(client):
    demo = start(client)
    token = client.post("/auth/demo/switch", headers=demo).json()["access_token"]
    colleague = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=colleague).json()["name"] == "Colega de grupo"
    assert client.post("/auth/demo/switch", headers=signup(client)).status_code == 404


def test_demo_and_real_accounts_never_find_each_other(client):
    real = signup(client)
    demo = start(client)
    real_code = client.get("/auth/me", headers=real).json()["code"]
    demo_code = client.get("/auth/me", headers=demo).json()["code"]
    assert client.get(f"/users/by-code/{real_code}", headers=demo).status_code == 404
    assert client.get(f"/users/by-code/{demo_code}", headers=real).status_code == 404
    other_demo = client.get("/auth/me", headers=start(client)).json()["code"]
    assert client.get(f"/users/by-code/{other_demo}", headers=demo).status_code == 404


def test_demo_accounts_cannot_log_in_with_a_password(client):
    demo = start(client)
    email = client.get("/auth/me", headers=demo).json()["email"]
    assert client.post("/auth/login", data={"username": email, "password": "qualquer-coisa"}).status_code == 401


def test_expired_demo_is_closed_and_removed(client):
    demo = start(client)
    with SessionLocal() as db:
        for user in db.scalars(select(User)):
            user.expires_at = now() - timedelta(minutes=1)
        db.commit()
    assert client.get("/auth/me", headers=demo).status_code == 401
    start(client)  # cada demonstração nova apaga as vencidas
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 2


def test_restart_removes_every_demo_and_old_fixed_accounts(client):
    real = signup(client)
    client.post("/articles", json={"title": "Meu", "template": "em-branco"}, headers=real)
    client.post("/auth/register", json={"name": "Demo antiga", "email": "demo@cronica.dev", "password": "demo-cronica", "accept_privacy": True})
    start(client)
    start(client)

    demo.reset_demo()

    with SessionLocal() as db:
        assert [u.email for u in db.scalars(select(User))] == ["ana@exemplo.com"]
        assert db.scalar(select(func.count()).select_from(Version)) == 1
        # Só sobra o arquivo do artigo da conta real.
        assert db.scalar(select(func.count()).select_from(Blob)) == 1
    assert len(client.get("/articles", headers=real).json()) == 1
