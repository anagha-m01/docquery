import pytest

from app.services import chat_service


def test_ask_question_raises_when_extraction_missing(monkeypatch):
    monkeypatch.setattr(chat_service, "get_extraction_for_reextract", lambda eid, uid: None)

    with pytest.raises(ValueError):
        chat_service.ask_question(999, "hi", user_id=1)


def test_ask_question_rejects_blank_question(monkeypatch):
    monkeypatch.setattr(chat_service, "get_extraction_for_reextract", lambda eid, uid: {"file_type": "csv"})

    with pytest.raises(ValueError):
        chat_service.ask_question(1, "   ", user_id=1)


def test_ask_question_tabular_lookup_uses_row_context(monkeypatch):
    """A specific, non-aggregate question still uses fast top-k vector
    search over rows rather than pulling the whole table."""
    monkeypatch.setattr(
        chat_service, "get_extraction_for_reextract", lambda eid, uid: {"file_type": "csv"}
    )
    monkeypatch.setattr(chat_service, "embed", lambda text: [0.1] * 384)
    monkeypatch.setattr(
        chat_service,
        "get_top_excel_rows",
        lambda eid, emb, top_k: [{"name": "Alice", "age": "30"}],
    )
    monkeypatch.setattr(chat_service, "get_chat_history", lambda eid: [])
    monkeypatch.setattr(
        chat_service, "answer_chat_question", lambda q, ctx, hist, extra="": "Alice is 30."
    )

    saved = []
    monkeypatch.setattr(
        chat_service,
        "save_chat_message",
        lambda eid, role, content: saved.append((eid, role, content)),
    )

    result = chat_service.ask_question(1, "How old is Alice?", user_id=1)

    assert result["answer"] == "Alice is 30."
    assert result["context_used"] == ["name: Alice | age: 30"]
    assert saved == [
        (1, "user", "How old is Alice?"),
        (1, "assistant", "Alice is 30."),
    ]


def test_ask_question_tabular_aggregate_uses_pandas_stats(monkeypatch):
    """'How many rows / what's the total' style questions should compute
    real statistics over the WHOLE table via pandas, not just search the
    top-k similar rows — and should never need an embedding call."""
    monkeypatch.setattr(
        chat_service, "get_extraction_for_reextract", lambda eid, uid: {"file_type": "csv"}
    )

    def boom_embed(text):
        raise AssertionError("embed() should not be called for an aggregate question")

    monkeypatch.setattr(chat_service, "embed", boom_embed)
    monkeypatch.setattr(
        chat_service,
        "get_all_excel_rows",
        lambda eid, limit: [
            {"name": "Alice", "amount": 10},
            {"name": "Bob", "amount": 20},
            {"name": "Cara", "amount": 30},
        ],
    )
    monkeypatch.setattr(chat_service, "get_chat_history", lambda eid: [])

    captured = {}

    def fake_answer(question, context_snippets, history, extra_instructions=""):
        captured["context"] = context_snippets
        captured["extra"] = extra_instructions
        return "The total is 60."

    monkeypatch.setattr(chat_service, "answer_chat_question", fake_answer)
    monkeypatch.setattr(chat_service, "save_chat_message", lambda eid, role, content: None)

    result = chat_service.ask_question(1, "What is the total amount?", user_id=1)

    assert result["answer"] == "The total is 60."
    joined = " ".join(captured["context"])
    assert "3 rows" in joined
    assert "sum=60" in joined
    assert "computed" in captured["extra"].lower()


def test_ask_question_tabular_list_all_is_treated_as_aggregate(monkeypatch):
    monkeypatch.setattr(
        chat_service, "get_extraction_for_reextract", lambda eid, uid: {"file_type": "xlsx"}
    )
    monkeypatch.setattr(
        chat_service, "get_all_excel_rows", lambda eid, limit: [{"name": "Alice"}]
    )
    monkeypatch.setattr(chat_service, "get_chat_history", lambda eid: [])
    monkeypatch.setattr(
        chat_service, "answer_chat_question", lambda q, ctx, hist, extra="": "Here they are."
    )
    monkeypatch.setattr(chat_service, "save_chat_message", lambda eid, role, content: None)

    result = chat_service.ask_question(1, "List all the records", user_id=1)

    assert result["answer"] == "Here they are."


def test_ask_question_pdf_uses_chunk_context(monkeypatch):
    monkeypatch.setattr(
        chat_service, "get_extraction_for_reextract", lambda eid, uid: {"file_type": "pdf"}
    )
    monkeypatch.setattr(chat_service, "embed", lambda text: [0.1] * 384)
    monkeypatch.setattr(
        chat_service, "get_top_pdf_chunks", lambda eid, emb, top_k: ["chunk text"]
    )
    monkeypatch.setattr(chat_service, "get_chat_history", lambda eid: [])
    monkeypatch.setattr(
        chat_service, "answer_chat_question", lambda q, ctx, hist, extra="": "answer"
    )
    monkeypatch.setattr(chat_service, "save_chat_message", lambda eid, role, content: None)

    result = chat_service.ask_question(2, "what is this doc about?", user_id=1)

    assert result["context_used"] == ["chunk text"]
    assert result["answer"] == "answer"


def test_ask_question_pdf_broad_question_uses_all_chunks(monkeypatch):
    monkeypatch.setattr(
        chat_service, "get_extraction_for_reextract", lambda eid, uid: {"file_type": "pdf"}
    )

    def boom_embed(text):
        raise AssertionError("embed() should not be called for a 'summarize everything' question")

    monkeypatch.setattr(chat_service, "embed", boom_embed)
    monkeypatch.setattr(
        chat_service, "get_all_pdf_chunks", lambda eid: ["chunk one", "chunk two", "chunk three"]
    )
    monkeypatch.setattr(chat_service, "get_chat_history", lambda eid: [])

    captured = {}

    def fake_answer(question, context_snippets, history, extra_instructions=""):
        captured["context"] = context_snippets
        return "Full summary."

    monkeypatch.setattr(chat_service, "answer_chat_question", fake_answer)
    monkeypatch.setattr(chat_service, "save_chat_message", lambda eid, role, content: None)

    result = chat_service.ask_question(2, "Summarize everything in this document", user_id=1)

    assert result["answer"] == "Full summary."
    assert captured["context"] == ["chunk one", "chunk two", "chunk three"]


def test_ask_question_handles_reextracted_file_type(monkeypatch):
    """file_type can be e.g. 'csv-reextract' after a re-extraction — the
    '-reextract' suffix should still be recognised as tabular."""
    monkeypatch.setattr(
        chat_service,
        "get_extraction_for_reextract",
        lambda eid, uid: {"file_type": "csv-reextract"},
    )
    monkeypatch.setattr(chat_service, "embed", lambda text: [0.1] * 384)
    monkeypatch.setattr(
        chat_service, "get_top_excel_rows", lambda eid, emb, top_k: [{"a": "1"}]
    )
    monkeypatch.setattr(chat_service, "get_chat_history", lambda eid: [])
    monkeypatch.setattr(
        chat_service, "answer_chat_question", lambda q, ctx, hist, extra="": "ok"
    )
    monkeypatch.setattr(chat_service, "save_chat_message", lambda eid, role, content: None)

    result = chat_service.ask_question(3, "q", user_id=1)

    assert result["context_used"] == ["a: 1"]


def test_get_history_raises_when_not_owned(monkeypatch):
    monkeypatch.setattr(chat_service, "get_extraction_for_reextract", lambda eid, uid: None)

    with pytest.raises(ValueError):
        chat_service.get_history(3, user_id=1)


def test_get_history_passes_limit(monkeypatch):
    monkeypatch.setattr(
        chat_service, "get_extraction_for_reextract", lambda eid, uid: {"file_type": "csv"}
    )
    captured = {}

    def fake_get_chat_history(eid, limit):
        captured["eid"] = eid
        captured["limit"] = limit
        return []

    monkeypatch.setattr(chat_service, "get_chat_history", fake_get_chat_history)

    chat_service.get_history(3, user_id=1)

    assert captured == {"eid": 3, "limit": 50}
    