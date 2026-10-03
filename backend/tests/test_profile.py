from sqlalchemy import create_engine, inspect, text

from tests.conftest import send, signup


def test_profile_starts_empty_and_counts_work(client):
    headers = signup(client)
    me = client.get("/auth/me", headers=headers).json()
    assert (me["institution"], me["articles"], me["versions"], me["last_activity"]) == ("", 0, 0, None)

    article = client.post("/articles", json={"title": "A", "template": "em-branco"}, headers=headers).json()
    send(client, headers, article["id"], {"main.tex": "\\documentclass{article}\\begin{document}Oi\\end{document}"},
         base=article["head"])
    me = client.get("/auth/me", headers=headers).json()
    assert (me["articles"], me["versions"]) == (1, 2)
    assert me["last_activity"]

    [listed] = client.get("/articles", headers=headers).json()
    assert listed["versions"] == 2 and listed["updated_at"]


def test_update_profile(client):
    headers = signup(client)
    response = client.patch("/auth/me", headers=headers, json={
        "institution": " UFPA ", "area": "IHC", "city": "Ananindeua, PA", "bio": "Pesquiso acessibilidade.",
    })
    assert response.status_code == 200
    me = client.get("/auth/me", headers=headers).json()
    assert (me["institution"], me["area"], me["city"], me["name"]) == ("UFPA", "IHC", "Ananindeua, PA", "Ana")


def test_update_profile_validates_sizes(client):
    headers = signup(client)
    assert client.patch("/auth/me", headers=headers, json={"name": ""}).status_code == 422
    assert client.patch("/auth/me", headers=headers, json={"bio": "x" * 1001}).status_code == 422


def test_old_database_gets_new_columns(tmp_path, monkeypatch):
    import app.database as database

    old = create_engine(f"sqlite:///{(tmp_path / 'antigo.db').as_posix()}")
    with old.begin() as connection:
        connection.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(120), email VARCHAR(255), "
            "password_hash VARCHAR(255), created_at DATETIME)"
        ))
        connection.execute(text("INSERT INTO users (name, email, password_hash) VALUES ('Ana', 'a@x.com', 'h')"))
    monkeypatch.setattr(database, "engine", old)

    database.create_schema()

    assert {"institution", "area", "city", "bio"} <= {c["name"] for c in inspect(old).get_columns("users")}
    with old.connect() as connection:
        assert connection.execute(text("SELECT institution FROM users")).scalar() == ""
    with old.connect() as connection:
        code, theme, picture = connection.execute(text("SELECT code, theme, picture FROM users")).one()
    assert len(code) == 9 and code[4] == "-" and theme == "azul" and picture is None
    assert "org_id" in {c["name"] for c in inspect(old).get_columns("articles")}


def test_choose_theme(client):
    headers = signup(client)
    assert client.get("/auth/me", headers=headers).json()["theme"] == "azul"
    assert client.patch("/auth/me", headers=headers, json={"theme": "noite"}).json()["theme"] == "noite"
    assert client.patch("/auth/me", headers=headers, json={"theme": "neon"}).status_code == 422


def test_customize_profile(client):
    headers = signup(client)
    me = client.patch("/auth/me", headers=headers, json={
        "status": " Escrevendo a dissertação ", "pattern": "bolinhas",
        "interests": ["IHC", " ihc ", "Acessibilidade  digital", ""],
        "lattes": "1234567890123456", "orcid": "0000-0002-1825-0097", "website": "meusite.com.br",
    }).json()
    assert me["status"] == "Escrevendo a dissertação" and me["pattern"] == "bolinhas"
    assert me["interests"] == ["IHC", "Acessibilidade digital"]
    assert me["lattes"] == "http://lattes.cnpq.br/1234567890123456"
    assert me["orcid"] == "https://orcid.org/0000-0002-1825-0097"
    assert me["website"] == "https://meusite.com.br"
    assert client.patch("/auth/me", headers=headers, json={"website": ""}).json()["website"] == ""


def test_customize_profile_rejects_bad_values(client):
    headers = signup(client)
    for bad in ({"lattes": "https://golpe.com/lattes"}, {"orcid": "123"}, {"website": "javascript:alert(1)"},
                {"pattern": "neon"}, {"status": "x" * 141}, {"interests": ["a"] * 11}):
        assert client.patch("/auth/me", headers=headers, json=bad).status_code == 422, bad


def test_old_database_moves_current_version_from_branches(tmp_path, monkeypatch):
    import app.database as database

    old = create_engine(f"sqlite:///{(tmp_path / 'antigo.db').as_posix()}")
    with old.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR, email VARCHAR, password_hash VARCHAR, created_at DATETIME)"))
        connection.execute(text("CREATE TABLE articles (id INTEGER PRIMARY KEY, title VARCHAR, owner_id INTEGER, created_at DATETIME)"))
        connection.execute(text("CREATE TABLE branches (id INTEGER PRIMARY KEY, article_id INTEGER, name VARCHAR, head_hash VARCHAR)"))
        connection.execute(text("INSERT INTO articles (id, title, owner_id) VALUES (7, 'A', 1)"))
        connection.execute(text("INSERT INTO branches (article_id, name, head_hash) VALUES (7, 'main', 'abc123')"))
    monkeypatch.setattr(database, "engine", old)

    database.create_schema()

    assert "branches" not in inspect(old).get_table_names()
    with old.connect() as connection:
        assert connection.execute(text("SELECT head_hash FROM articles WHERE id = 7")).scalar() == "abc123"
