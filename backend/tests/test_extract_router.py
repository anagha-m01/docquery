import io


def test_extract_rejects_unsupported_file_type(client):
    res = client.post(
        "/extract",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert res.status_code == 400
    assert "Unsupported file type" in res.json()["detail"]


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


def test_extract_returns_500_on_unexpected_error(client, monkeypatch):
    def boom(path, filename):
        raise RuntimeError("groq is down")

    monkeypatch.setattr("app.routers.extract.process_file", boom)

    res = client.post(
        "/extract",
        files={"file": ("resume.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )

    assert res.status_code == 500
    assert "Extraction failed" in res.json()["detail"]
