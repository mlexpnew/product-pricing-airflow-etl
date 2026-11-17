import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


def test_api(tmp_path, monkeypatch):
    db = f"sqlite:///{tmp_path}/sw.db"
    monkeypatch.setenv("SHELFWATCH_DB", db)
    from shelfwatch.demo import build
    from shelfwatch.store import Store

    build(Store(db), 3)
    from shelfwatch.api import app

    c = TestClient(app)
    assert c.get("/health").json() == {"status": "ok"}
    assert len(c.get("/v1/runs").json()) == 4
    assert c.post("/v1/undercuts", json={"prices": {"x": 10.0}}).json() == []
