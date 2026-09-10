"""
chat_service.py
─────────────────
New: lets the user ask free-form questions about a previously uploaded
file. Reuses the exact same retrieval machinery as /reextract —
embed the question, pull the top-k most relevant chunks (PDF) or rows
(Excel/CSV) from pgvector, hand them to the LLM as context, and persist
the conversation so follow-up questions have history to work with.
"""

from app.core.config import settings
from app.core.database import (
    get_extraction_for_reextract,
    get_top_pdf_chunks,
    get_top_excel_rows,
    save_chat_message,
    get_chat_history,
)
from app.services.embedding_service import embed
from app.services.llm_service import answer_chat_question


def ask_question(extraction_id: int, question: str) -> dict:
    row = get_extraction_for_reextract(extraction_id)
    if not row:
        raise ValueError("Extraction not found.")

    file_type = row["file_type"]
    is_tabular = file_type.replace("-reextract", "") in settings.TABULAR_TYPES

    query_embedding = embed(question)

    if is_tabular:
        top_rows = get_top_excel_rows(extraction_id, query_embedding, top_k=settings.TOP_K_CHAT)
        context_snippets = [
            " | ".join(f"{k}: {v}" for k, v in r.items()) for r in top_rows
        ]
    else:
        context_snippets = get_top_pdf_chunks(extraction_id, query_embedding, top_k=settings.TOP_K_CHAT)

    history = get_chat_history(extraction_id)

    answer = answer_chat_question(question, context_snippets, history)

    # Persist both turns so the next question has this one as context
    save_chat_message(extraction_id, "user", question)
    save_chat_message(extraction_id, "assistant", answer)

    return {"answer": answer, "context_used": context_snippets}


def get_history(extraction_id: int) -> list[dict]:
    return get_chat_history(extraction_id, limit=50)
