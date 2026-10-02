import os

# Not required for these tests — every Groq/DB call is mocked at the
# router/service level — but set so app.core.config never has an
# empty-string surprise if a startup check on these is added later.
os.environ.setdefault("GROQ_API_KEY", "test-dummy-key")
os.environ.setdefault("JWT_SECRET", "test-secret-key-not-for-production")

import pytest
from fastapi.testclient import TestClient


FAKE_USER = {"id": 1, "email": "test@example.com"}
OTHER_USER = {"id": 2, "email": "someone-else@example.com"}


@pytest.fixture
def client(monkeypatch):
    """
    TestClient with the real Postgres/pgvector startup call disabled, and
    auth short-circuited to a fixed fake user (id=1) so most tests don't
    need to deal with real JWTs — they just exercise ownership logic via
    whatever `current_user["id"]` the mocked DB functions receive.

    Tests that need to exercise real login/registration/token flows use
    `raw_client` instead, which leaves auth untouched.
    """
    monkeypatch.setattr("app.main.init_db", lambda: None)
    from app.main import app
    from app.core.deps import get_current_user

    app.dependency_overrides[get_current_user] = lambda: FAKE_USER

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def raw_client(monkeypatch):
    """TestClient with NO auth override — for testing register/login/401s."""
    monkeypatch.setattr("app.main.init_db", lambda: None)
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def current_user():
    return dict(FAKE_USER)


@pytest.fixture
def other_user():
    return dict(OTHER_USER)
    