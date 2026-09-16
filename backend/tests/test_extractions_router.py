def test_list_extractions(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.extractions.get_all_extractions",
        lambda: [{"id": 1, "filename": "a.pdf"}],
    )

    res = client.get("/extractions")

    assert res.status_code == 200
    assert res.json() == {"extractions": [{"id": 1, "filename": "a.pdf"}]}


def test_get_extraction_found(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.extractions.get_extraction_by_id",
        lambda eid: {"id": eid, "filename": "a.pdf"},
    )

    res = client.get("/extractions/5")

    assert res.status_code == 200
    assert res.json()["id"] == 5


def test_get_extraction_not_found(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.extractions.get_extraction_by_id", lambda eid: None
    )

    res = client.get("/extractions/999")

    assert res.status_code == 404
