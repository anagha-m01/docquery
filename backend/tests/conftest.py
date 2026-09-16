import os

# Not required for these tests — every Groq call is mocked at the router/
# service level — but set so app.core.config never has an empty-string
# surprise if a startup check on this variable is added later.
os.environ.setdefault("GROQ_API_KEY", "test-dummy-key")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    """
    TestClient with the real Postgres/pgvector startup call disabled.

    app.main's lifespan calls init_db(), which opens a real psycopg2
    connection on startup. Patching it out here means this suite never
    needs a live Postgres instance.
    """
    monkeypatch.setattr("app.main.init_db", lambda: None)
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
        