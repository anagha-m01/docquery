def test_reextract_returns_404_when_extraction_missing(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.reextract.get_extraction_for_reextract", lambda eid, uid: None
    )

    res = client.post(
        "/reextract",
        json={"extraction_id": 999, "schema": {"name": "string"}, "filename": "x.csv"},
    )

    assert res.status_code == 404


def test_reextract_requires_auth(raw_client):
    res = raw_client.post(
        "/reextract",
        json={"extraction_id": 1, "schema": {"name": "string"}, "filename": "x.csv"},
    )
    assert res.status_code == 401


def test_reextract_rejects_empty_schema(client):
    res = client.post(
        "/reextract",
        json={"extraction_id": 1, "schema": {}, "filename": "x.csv"},
    )
    assert res.status_code == 422


def test_reextract_tabular_success(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.reextract.get_extraction_for_reextract",
        lambda eid, uid: {"file_type": "csv", "raw_text": None, "data": []},
    )
    monkeypatch.setattr("app.routers.reextract.embed", lambda text: [0.1] * 384)
    monkeypatch.setattr(
        "app.routers.reextract.get_top_excel_rows",
        lambda eid, emb, top_k: [{"name": "Alice", "age": "30"}],
    )
    monkeypatch.setattr(
        "app.routers.reextract.save_extraction", lambda **kwargs: 42
    )

    res = client.post(
        "/reextract",
        json={"extraction_id": 1, "schema": {"name": "string"}, "filename": "people.csv"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == 42
    # Result is filtered down to just the keys in the requested schema
    assert body["data"] == [{"name": "Alice"}]


def test_reextract_tabular_no_rows_returns_400(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.reextract.get_extraction_for_reextract",
        lambda eid, uid: {"file_type": "xlsx", "raw_text": None, "data": []},
    )
    monkeypatch.setattr("app.routers.reextract.embed", lambda text: [0.1] * 384)
    monkeypatch.setattr(
        "app.routers.reextract.get_top_excel_rows", lambda eid, emb, top_k: []
    )

    res = client.post(
        "/reextract",
        json={"extraction_id": 1, "schema": {"name": "string"}, "filename": "people.xlsx"},
    )

    assert res.status_code == 400


def test_reextract_pdf_success(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.reextract.get_extraction_for_reextract",
        lambda eid, uid: {"file_type": "pdf", "raw_text": "full text", "data": []},
    )
    monkeypatch.setattr("app.routers.reextract.embed", lambda text: [0.1] * 384)
    monkeypatch.setattr(
        "app.routers.reextract.get_top_pdf_chunks",
        lambda eid, emb, top_k: ["chunk one"],
    )
    monkeypatch.setattr(
        "app.routers.reextract.extract_chunk_with_schema",
        lambda chunk, schema, chunk_index, total_chunks: {"name": "Bob"},
    )
    monkeypatch.setattr(
        "app.routers.reextract.merge_chunk_results",
        lambda chunk_extractions, source_text="", schema=None: {"name": "Bob"},
    )
    monkeypatch.setattr(
        "app.routers.reextract.save_extraction", lambda **kwargs: 7
    )

    res = client.post(
        "/reextract",
        json={"extraction_id": 5, "schema": {"name": "string"}, "filename": "resume.pdf"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == 7
    assert body["data"] == {"name": "Bob"}


def test_reextract_pdf_no_chunks_returns_400(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.reextract.get_extraction_for_reextract",
        lambda eid, uid: {"file_type": "pdf", "raw_text": "full text", "data": []},
    )
    monkeypatch.setattr("app.routers.reextract.embed", lambda text: [0.1] * 384)
    monkeypatch.setattr(
        "app.routers.reextract.get_top_pdf_chunks", lambda eid, emb, top_k: []
    )

    res = client.post(
        "/reextract",
        json={"extraction_id": 5, "schema": {"name": "string"}, "filename": "resume.pdf"},
    )

    assert res.status_code == 400


def test_reextract_returns_500_on_unexpected_error(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.reextract.get_extraction_for_reextract",
        lambda eid, uid: {"file_type": "csv", "raw_text": None, "data": []},
    )

    def boom(text):
        raise RuntimeError("something odd")

    monkeypatch.setattr("app.routers.reextract.embed", boom)

    res = client.post(
        "/reextract",
        json={"extraction_id": 1, "schema": {"name": "string"}, "filename": "people.csv"},
    )

    assert res.status_code == 500


def test_reextract_returns_503_on_embedding_failure(client, monkeypatch):
    from app.services.embedding_service import EmbeddingServiceError

    monkeypatch.setattr(
        "app.routers.reextract.get_extraction_for_reextract",
        lambda eid, uid: {"file_type": "csv", "raw_text": None, "data": []},
    )

    def boom(text):
        raise EmbeddingServiceError("Could not process this text for search. Please try again.")

    monkeypatch.setattr("app.routers.reextract.embed", boom)

    res = client.post(
        "/reextract",
        json={"extraction_id": 1, "schema": {"name": "string"}, "filename": "people.csv"},
    )

    assert res.status_code == 503
    