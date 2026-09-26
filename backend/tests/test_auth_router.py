from app.core.database import DuplicateEmailError
from app.core.security import hash_password


def test_register_creates_user_and_returns_token(raw_client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.create_user", lambda email, pw_hash: 1)

    res = raw_client.post(
        "/auth/register", json={"email": "new@example.com", "password": "supersecret1"}
    )

    assert res.status_code == 201
    body = res.json()
    assert body["user"] == {"id": 1, "email": "new@example.com"}
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_register_rejects_short_password(raw_client):
    res = raw_client.post(
        "/auth/register", json={"email": "new@example.com", "password": "short"}
    )
    assert res.status_code == 422


def test_register_rejects_invalid_email(raw_client):
    res = raw_client.post(
        "/auth/register", json={"email": "not-an-email", "password": "supersecret1"}
    )
    assert res.status_code == 422


def test_register_rejects_duplicate_email(raw_client, monkeypatch):
    def boom(email, pw_hash):
        raise DuplicateEmailError("An account with this email already exists.")

    monkeypatch.setattr("app.routers.auth.create_user", boom)

    res = raw_client.post(
        "/auth/register", json={"email": "taken@example.com", "password": "supersecret1"}
    )

    assert res.status_code == 409


def test_login_succeeds_with_correct_password(raw_client, monkeypatch):
    stored_hash = hash_password("supersecret1")
    monkeypatch.setattr(
        "app.routers.auth.get_user_by_email",
        lambda email: {"id": 5, "email": email, "password_hash": stored_hash},
    )

    res = raw_client.post(
        "/auth/login", json={"email": "user@example.com", "password": "supersecret1"}
    )

    assert res.status_code == 200
    body = res.json()
    assert body["user"] == {"id": 5, "email": "user@example.com"}
    assert body["access_token"]


def test_login_rejects_wrong_password(raw_client, monkeypatch):
    stored_hash = hash_password("supersecret1")
    monkeypatch.setattr(
        "app.routers.auth.get_user_by_email",
        lambda email: {"id": 5, "email": email, "password_hash": stored_hash},
    )

    res = raw_client.post(
        "/auth/login", json={"email": "user@example.com", "password": "wrong-password"}
    )

    assert res.status_code == 401


def test_login_rejects_unknown_email(raw_client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.get_user_by_email", lambda email: None)

    res = raw_client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever1"}
    )

    assert res.status_code == 401


def test_me_requires_valid_token(raw_client):
    res = raw_client.get("/auth/me")
    assert res.status_code == 401

    res = raw_client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 401


def test_me_returns_current_user_with_valid_token(raw_client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.create_user", lambda email, pw_hash: 9)
    register_res = raw_client.post(
        "/auth/register", json={"email": "me@example.com", "password": "supersecret1"}
    )
    token = register_res.json()["access_token"]

    monkeypatch.setattr(
        "app.core.deps.get_user_by_id",
        lambda user_id: {"id": 9, "email": "me@example.com"},
    )

    res = raw_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    assert res.json() == {"id": 9, "email": "me@example.com"}
    