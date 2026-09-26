import time

import jwt
import pytest

from app.core import security


def test_hash_password_and_verify_roundtrip():
    hashed = security.hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert security.verify_password("correct-horse-battery-staple", hashed)


def test_verify_password_rejects_wrong_password():
    hashed = security.hash_password("correct-horse-battery-staple")
    assert not security.verify_password("wrong-password", hashed)


def test_verify_password_handles_garbage_hash_gracefully():
    # Should never raise — just report False for a hash that isn't valid bcrypt.
    assert not security.verify_password("anything", "not-a-real-bcrypt-hash")


def test_create_and_decode_access_token_roundtrip():
    token = security.create_access_token(user_id=7, email="a@b.com")
    payload = security.decode_access_token(token)

    assert payload["sub"] == "7"
    assert payload["email"] == "a@b.com"


def test_decode_access_token_rejects_tampered_token():
    token = security.create_access_token(user_id=7, email="a@b.com")
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")

    with pytest.raises(jwt.PyJWTError):
        security.decode_access_token(tampered)


def test_decode_access_token_rejects_expired_token(monkeypatch):
    monkeypatch.setattr(security.settings, "JWT_EXPIRE_MINUTES", 0)
    token = security.create_access_token(user_id=7, email="a@b.com")

    time.sleep(1.1)

    with pytest.raises(jwt.ExpiredSignatureError):
        security.decode_access_token(token)
        