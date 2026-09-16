import React, { useEffect, useRef, useState } from "react";
import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function Chat({ extractionId, filename }) {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);

  // Load existing conversation whenever the active extraction changes.
  useEffect(() => {
    if (!extractionId) {
      setMessages([]);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const res = await axios.get(`${API_URL}/chat/${extractionId}`);
        if (!cancelled) setMessages(res.data.messages || []);
      } catch (err) {
        if (!cancelled) setMessages([]);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [extractionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  const handleSend = async (e) => {
    e.preventDefault();
    const q = question.trim();
    if (!q || !extractionId || sending) return;

    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setQuestion("");
    setSending(true);

    try {
      const res = await axios.post(`${API_URL}/chat`, {
        extraction_id: extractionId,
        question: q,
      });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.data.answer },
      ]);
    } catch (err) {
      const msg =
        err.response?.data?.detail || err.message || "Chat request failed.";
      setError(msg);
    } finally {
      setSending(false);
    }
  };

  if (!extractionId) {
    return (
      <div className="chat-block chat-empty-state">
        <span className="chat-empty-icon">💬</span>
        <p>Upload a file (or pick one from History) to start asking questions.</p>
      </div>
    );
  }

  return (
    <div className="chat-block">
      <div className="result-header">
        <h3>Ask about {filename || "this document"}</h3>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && !sending && (
          <div className="chat-hint">
            Ask anything about this document — e.g. "What's the total on
            invoice 3?" or "Summarize the key figures."
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`chat-msg chat-msg-${m.role}`}>
            <span className="chat-msg-role">
              {m.role === "user" ? "You" : "DocQuery"}
            </span>
            <p>{m.content}</p>
          </div>
        ))}

        {sending && (
          <div className="chat-msg chat-msg-assistant chat-msg-pending">
            <span className="chat-msg-role">DocQuery</span>
            <p>
              <span className="chat-dot" />
              <span className="chat-dot" />
              <span className="chat-dot" />
            </p>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {error && (
        <div className="error-banner chat-error">
          <span className="error-icon">⚠</span>
          {error}
        </div>
      )}

      <form className="chat-input-row" onSubmit={handleSend}>
        <input
          type="text"
          className="chat-input"
          placeholder="Ask a question about this file…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={sending}
        />
        <button
          type="submit"
          className="chat-send-btn"
          disabled={sending || !question.trim()}
        >
          {sending ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}

export default Chat;

