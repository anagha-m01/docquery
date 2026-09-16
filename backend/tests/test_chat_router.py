def test_chat_returns_answer(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.chat_service.ask_question",
        lambda extraction_id, question: {
            "answer": "It's 30.",
            "context_used": ["Alice, 30"],
        },
    )

    res = client.post("/chat", json={"extraction_id": 1, "question": "How old is Alice?"})

    assert res.status_code == 200
    assert res.json() == {"answer": "It's 30.", "context_used": ["Alice, 30"]}


def test_chat_returns_404_when_extraction_missing(client, monkeypatch):
    def boom(extraction_id, question):
        raise ValueError("Extraction not found.")

    monkeypatch.setattr("app.services.chat_service.ask_question", boom)

    res = client.post("/chat", json={"extraction_id": 999, "question": "hi"})

    assert res.status_code == 404


def test_chat_returns_500_on_unexpected_error(client, monkeypatch):
    def boom(extraction_id, question):
        raise RuntimeError("groq is down")

    monkeypatch.setattr("app.services.chat_service.ask_question", boom)

    res = client.post("/chat", json={"extraction_id": 1, "question": "hi"})

    assert res.status_code == 500


def test_chat_history_returns_messages(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.chat_service.get_history",
        lambda extraction_id: [{"role": "user", "content": "hi"}],
    )

    res = client.get("/chat/1")

    assert res.status_code == 200
    assert res.json() == {"messages": [{"role": "user", "content": "hi"}]}
