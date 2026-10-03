import io
import os
import zipfile
from pathlib import Path

# Padrão: SQLite num arquivo temporário. No GitHub Actions, DATABASE_URL aponta para o PostgreSQL.
os.environ.setdefault("DATABASE_URL", "sqlite:///" + (Path(__file__).parent / "test.db").as_posix())

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app
from app.security import attempts


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    attempts.clear()  # o limite de tentativas de login vale por teste, não para a bateria inteira
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def make_zip(files: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buffer.getvalue()


def signup(client, email="ana@exemplo.com"):
    client.post("/auth/register", json={"name": "Ana", "email": email, "password": "senha-segura", "accept_privacy": True})
    token = client.post("/auth/login", data={"username": email, "password": "senha-segura"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def send(client, headers, article_id, files, message="versão", base=None):
    data = {"message": message}
    if base:
        data["base_version"] = base
    return client.post(
        f"/articles/{article_id}/versions",
        headers=headers, data=data,
        files={"file": ("projeto.zip", make_zip(files), "application/zip")},
    )
