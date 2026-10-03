import threading

import pytest

from app import versioning
from app.database import IS_SQLITE, SessionLocal
from app.models import Article, User


# O SQLite não tem SELECT ... FOR UPDATE; este teste roda no PostgreSQL (GitHub Actions).
@pytest.mark.skipif(IS_SQLITE, reason="precisa do PostgreSQL")
def test_two_commits_on_same_base_only_one_wins():
    with SessionLocal() as db:
        user = User(name="Ana", email="ana@exemplo.com", password_hash="x")
        db.add(user)
        db.commit()
        article = versioning.create_article(db, "Artigo", user)
        base = versioning.commit(db, article, {"main.tex": b"v1"}, "v1", None, user).hash

    barrier = threading.Barrier(2)
    results = []

    def attempt(text: bytes):
        with SessionLocal() as db:
            barrier.wait()
            try:
                versioning.commit(db, db.get(Article, article.id), {"main.tex": text}, "paralelo", base, db.get(User, user.id))
                results.append("ok")
            except versioning.CommitConflict:
                db.rollback()
                results.append("conflito")

    threads = [threading.Thread(target=attempt, args=(t,)) for t in (b"versao A", b"versao B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == ["conflito", "ok"]
