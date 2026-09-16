import pytest

from app.services import chat_service


def test_ask_question_raises_when_extraction_missing(monkeypatch):
    monkeypatch.setattr(chat_service, "get_extraction_for_reextract", lambda eid: None)

    with pytest.raises(ValueError):
        chat_service.ask_question(999, "hi")


def test_ask_question_tabular_uses_row_context(monkeypatch):
    monkeypatch.setattr(
        chat_service, "get_extraction_for_reextract", lambda eid: {"file_type": "csv"}
    )
    monkeypatch.setattr(chat_service, "embed", lambda text: [0.1] * 384)
    monkeypatch.setattr(
        chat_service,
        "get_top_excel_rows",
        lambda eid, emb, top_k: [{"name": "Alice", "age": "30"}],
    )
    monkeypatch.setattr(chat_service, "get_chat_history", lambda eid: [])
    monkeypatch.setattr(
        chat_service, "answer_chat_question", lambda q, ctx, hist: "Alice is 30."
    )

    saved = []
    monkeypatch.setattr(
        chat_service,
        "save_chat_message",
        lambda eid, role, content: saved.append((eid, role, content)),
    )

    result = chat_service.ask_question(1, "How old is Alice?")

    assert result["answer"] == "Alice is 30."
    assert result["context_used"] == ["name: Alice | age: 30"]
    assert saved == [
        (1, "user", "How old is Alice?"),
        (1, "assistant", "Alice is 30."),
    ]


def test_ask_question_pdf_uses_chunk_context(monkeypatch):
    monkeypatch.setattr(
        chat_service, "get_extraction_for_reextract", lambda eid: {"file_type": "pdf"}
    )
    monkeypatch.setattr(chat_service, "embed", lambda text: [0.1] * 384)
    monkeypatch.setattr(
        chat_service, "get_top_pdf_chunks", lambda eid, emb, top_k: ["chunk text"]
    )
    monkeypatch.setattr(chat_service, "get_chat_history", lambda eid: [])
    monkeypatch.setattr(chat_service, "answer_chat_question", lambda q, ctx, hist: "answer")
    monkeypatch.setattr(chat_service, "save_chat_message", lambda eid, role, content: None)

    result = chat_service.ask_question(2, "what is this doc about?")

    assert result["context_used"] == ["chunk text"]
    assert result["answer"] == "answer"


def test_ask_question_handles_reextracted_file_type(monkeypatch):
    """file_type can be e.g. 'csv-reextract' after a re-extraction — the
    '-reextract' suffix should still be recognised as tabular."""
    monkeypatch.setattr(
        chat_service,
        "get_extraction_for_reextract",
        lambda eid: {"file_type": "csv-reextract"},
    )
    monkeypatch.setattr(chat_service, "embed", lambda text: [0.1] * 384)
    monkeypatch.setattr(
        chat_service, "get_top_excel_rows", lambda eid, emb, top_k: [{"a": "1"}]
    )
    monkeypatch.setattr(chat_service, "get_chat_history", lambda eid: [])
    monkeypatch.setattr(chat_service, "answer_chat_question", lambda q, ctx, hist: "ok")
    monkeypatch.setattr(chat_service, "save_chat_message", lambda eid, role, content: None)

    result = chat_service.ask_question(3, "q")

    assert result["context_used"] == ["a: 1"]


def test_get_history_passes_limit(monkeypatch):
    captured = {}

    def fake_get_chat_history(eid, limit):
        captured["eid"] = eid
        captured["limit"] = limit
        return []

    monkeypatch.setattr(chat_service, "get_chat_history", fake_get_chat_history)

    chat_service.get_history(3)

    assert captured == {"eid": 3, "limit": 50}
