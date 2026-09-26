import io


def test_extract_requires_auth(raw_client):
    res = raw_client.post(
        "/extract",
        files={"file": ("resume.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )
    assert res.status_code == 401


def test_extract_rejects_unsupported_file_type(client):
    res = client.post(
        "/extract",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert res.status_code == 400
    assert "Unsupported file type" in res.json()["detail"]


def test_extract_rejects_empty_file(client):
    res = client.post(
        "/extract",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()


def test_extract_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.MAX_UPLOAD_BYTES", 10)

    res = client.post(
        "/extract",
        files={"file": ("big.csv", io.BytesIO(b"a,b\n" * 100), "text/csv")},
    )
    assert res.status_code == 413


def test_extract_pdf_success(client, monkeypatch):
    fake_result = {"schema": {"name": "string"}, "data": [{"name": "Alice"}]}

    monkeypatch.setattr(
        "app.routers.extract.process_file",
        lambda path, filename: fake_result,
    )
    monkeypatch.setattr(
        "app.routers.extract.extract_text_from_pdf", lambda path: "Alice, 30"
    )
    monkeypatch.setattr(
        "app.routers.extract.get_chunks", lambda text: ["Alice, 30"]
    )
    monkeypatch.setattr(
        "app.routers.extract.embed_batch", lambda texts: [[0.1] * 384]
    )
    monkeypatch.setattr(
        "app.routers.extract.save_extraction", lambda **kwargs: 1
    )

    saved_chunks = {}

    def fake_save_pdf_chunks(row_id, chunks, embeddings):
        saved_chunks["row_id"] = row_id
        saved_chunks["chunks"] = chunks

    monkeypatch.setattr(
        "app.routers.extract.save_pdf_chunks", fake_save_pdf_chunks
    )

    res = client.post(
        "/extract",
        files={"file": ("resume.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == 1
    assert body["data"] == fake_result
    assert saved_chunks == {"row_id": 1, "chunks": ["Alice, 30"]}


def test_extract_excel_success(client, monkeypatch):
    rows = [{"col_a": "1", "col_b": "2"}]
    fake_result = {"schema": {"col_a": "string"}, "data": rows, "rows": rows}

    monkeypatch.setattr(
        "app.routers.extract.process_file",
        lambda path, filename: fake_result,
    )
    monkeypatch.setattr(
        "app.routers.extract.embed_batch", lambda texts: [[0.1] * 384]
    )
    monkeypatch.setattr(
        "app.routers.extract.save_extraction", lambda **kwargs: 2
    )

    saved = {}

    def fake_save_excel_rows(row_id, rows_, embeddings):
        saved["row_id"] = row_id
        saved["rows"] = rows_

    monkeypatch.setattr(
        "app.routers.extract.save_excel_rows", fake_save_excel_rows
    )

    res = client.post(
        "/extract",
        files={"file": ("data.csv", io.BytesIO(b"col_a,col_b\n1,2"), "text/csv")},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == 2
    assert body["data"] == fake_result
    assert saved == {"row_id": 2, "rows": rows}


def test_extract_allows_duplicate_filenames(client, monkeypatch):
    """Uploading the same filename twice creates two independent
    extractions — there's no uniqueness constraint on filename, only on
    the generated row id."""
    rows = [{"col_a": "1"}]
    fake_result = {"schema": {"col_a": "string"}, "data": rows, "rows": rows}

    monkeypatch.setattr("app.routers.extract.process_file", lambda path, filename: fake_result)
    monkeypatch.setattr("app.routers.extract.embed_batch", lambda texts: [[0.1] * 384])
    monkeypatch.setattr("app.routers.extract.save_excel_rows", lambda row_id, rows_, embeddings: None)

    ids = iter([10, 11])
    monkeypatch.setattr("app.routers.extract.save_extraction", lambda **kwargs: next(ids))

    res1 = client.post("/extract", files={"file": ("data.csv", io.BytesIO(b"col_a\n1"), "text/csv")})
    res2 = client.post("/extract", files={"file": ("data.csv", io.BytesIO(b"col_a\n1"), "text/csv")})

    assert res1.status_code == 200 and res2.status_code == 200
    assert res1.json()["id"] != res2.json()["id"]


def test_extract_returns_500_on_unexpected_error(client, monkeypatch):
    def boom(path, filename):
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr("app.routers.extract.process_file", boom)

    res = client.post(
        "/extract",
        files={"file": ("resume.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )

    assert res.status_code == 500
    assert "Extraction failed" in res.json()["detail"]


def test_extract_returns_400_on_corrupt_or_password_protected_pdf(client, monkeypatch):
    def boom(path, filename):
        raise ValueError("This PDF is password-protected. Please upload an unlocked copy.")

    monkeypatch.setattr("app.routers.extract.process_file", boom)

    res = client.post(
        "/extract",
        files={"file": ("locked.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )

    assert res.status_code == 400
    assert "password-protected" in res.json()["detail"].lower()


def test_extract_returns_503_on_embedding_failure(client, monkeypatch):
    from app.services.embedding_service import EmbeddingServiceError

    fake_result = {"schema": {"col_a": "string"}, "data": [{"col_a": "1"}], "rows": [{"col_a": "1"}]}
    monkeypatch.setattr("app.routers.extract.process_file", lambda path, filename: fake_result)

    def boom(texts):
        raise EmbeddingServiceError("Could not process this file's content for search. Please try again.")

    monkeypatch.setattr("app.routers.extract.embed_batch", boom)

    res = client.post(
        "/extract",
        files={"file": ("data.csv", io.BytesIO(b"col_a\n1"), "text/csv")},
    )

    assert res.status_code == 503
    