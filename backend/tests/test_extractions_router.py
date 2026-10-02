def test_list_extractions(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.extractions.get_all_extractions",
        lambda user_id: [{"id": 1, "filename": "a.pdf"}],
    )

    res = client.get("/extractions")

    assert res.status_code == 200
    assert res.json() == {"extractions": [{"id": 1, "filename": "a.pdf"}]}


def test_list_extractions_requires_auth(raw_client):
    res = raw_client.get("/extractions")
    assert res.status_code == 401


def test_get_extraction_found(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.extractions.get_extraction_by_id",
        lambda eid, uid: {"id": eid, "filename": "a.pdf"},
    )

    res = client.get("/extractions/5")

    assert res.status_code == 200
    assert res.json()["id"] == 5


def test_get_extraction_not_found(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.extractions.get_extraction_by_id", lambda eid, uid: None
    )

    res = client.get("/extractions/999")

    assert res.status_code == 404


def test_get_extraction_owned_by_someone_else_returns_404(client, monkeypatch):
    """The DB layer filters by user_id, so a file that exists but belongs
    to another user comes back as None here too — the router can't tell
    (and shouldn't be able to tell) the difference from non-existence."""
    monkeypatch.setattr(
        "app.routers.extractions.get_extraction_by_id", lambda eid, uid: None
    )

    res = client.get("/extractions/42")

    assert res.status_code == 404


def test_delete_extraction_success(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.extractions.delete_extraction", lambda eid, uid: True
    )

    res = client.delete("/extractions/1")

    assert res.status_code == 200
    assert res.json() == {"deleted": True, "id": 1}


def test_delete_extraction_not_found_or_not_owned(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.extractions.delete_extraction", lambda eid, uid: False
    )

    res = client.delete("/extractions/999")

    assert res.status_code == 404


def test_delete_extraction_requires_auth(raw_client):
    res = raw_client.delete("/extractions/1")
    assert res.status_code == 401


def test_extractions_returns_503_on_db_failure(client, monkeypatch):
    from app.core.database import DatabaseError

    def boom(user_id):
        raise DatabaseError("Could not connect to the database. Please try again shortly.")

    monkeypatch.setattr("app.routers.extractions.get_all_extractions", boom)

    res = client.get("/extractions")

    assert res.status_code == 503
    