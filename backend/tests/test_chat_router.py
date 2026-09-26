def test_chat_returns_answer(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.chat_service.ask_question",
        lambda extraction_id, question, user_id: {
            "answer": "It's 30.",
            "context_used": ["Alice, 30"],
        },
    )

    res = client.post("/chat", json={"extraction_id": 1, "question": "How old is Alice?"})

    assert res.status_code == 200
    assert res.json() == {"answer": "It's 30.", "context_used": ["Alice, 30"]}


def test_chat_rejects_empty_question(client):
    res = client.post("/chat", json={"extraction_id": 1, "question": "   "})
    assert res.status_code == 422


def test_chat_returns_404_when_extraction_missing(client, monkeypatch):
    def boom(extraction_id, question, user_id):
        raise ValueError("Extraction not found.")

    monkeypatch.setattr("app.services.chat_service.ask_question", boom)

    res = client.post("/chat", json={"extraction_id": 999, "question": "hi"})

    assert res.status_code == 404


def test_chat_returns_500_on_unexpected_error(client, monkeypatch):
    def boom(extraction_id, question, user_id):
        raise RuntimeError("groq is down")

    monkeypatch.setattr("app.services.chat_service.ask_question", boom)

    res = client.post("/chat", json={"extraction_id": 1, "question": "hi"})

    assert res.status_code == 500


def test_chat_returns_503_on_llm_failure(client, monkeypatch):
    from app.services.llm_service import LLMServiceError

    def boom(extraction_id, question, user_id):
        raise LLMServiceError("The AI service is temporarily unavailable. Please try again in a moment.")

    monkeypatch.setattr("app.services.chat_service.ask_question", boom)

    res = client.post("/chat", json={"extraction_id": 1, "question": "hi"})

    assert res.status_code == 503


def test_chat_requires_auth(raw_client):
    res = raw_client.post("/chat", json={"extraction_id": 1, "question": "hi"})
    assert res.status_code == 401


def test_chat_history_returns_messages(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.chat_service.get_history",
        lambda extraction_id, user_id: [{"role": "user", "content": "hi"}],
    )

    res = client.get("/chat/1")

    assert res.status_code == 200
    assert res.json() == {"messages": [{"role": "user", "content": "hi"}]}


def test_chat_history_returns_404_for_someone_elses_extraction(client, monkeypatch):
    def boom(extraction_id, user_id):
        raise ValueError("Extraction not found.")

    monkeypatch.setattr("app.services.chat_service.get_history", boom)

    res = client.get("/chat/1")

    assert res.status_code == 404