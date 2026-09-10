"""
database.py
───────────
PostgreSQL + pgvector database layer. Raw psycopg2 — no ORM, kept
deliberately simple for this project's scale.

Tables:
  extractions    — main extraction results (schema, data, raw_text)
  pdf_chunks     — PDF text chunks with embeddings (for smart re-extract / chat)
  excel_rows     — Excel/CSV rows with embeddings (for semantic row search)
  chat_messages  — chat history per extraction (for the /chat feature)
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

from app.core.config import settings


def get_connection():
    return psycopg2.connect(**settings.db_config)


def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS extractions (
                    id          SERIAL PRIMARY KEY,
                    filename    TEXT NOT NULL,
                    file_type   TEXT NOT NULL,
                    schema      JSONB,
                    data        JSONB,
                    raw_text    TEXT,
                    status      TEXT DEFAULT 'done',
                    created_at  TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("ALTER TABLE extractions ADD COLUMN IF NOT EXISTS raw_text TEXT;")
            cur.execute("ALTER TABLE extractions ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'done';")

            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS pdf_chunks (
                    id              SERIAL PRIMARY KEY,
                    extraction_id   INT REFERENCES extractions(id) ON DELETE CASCADE,
                    chunk_index     INT NOT NULL,
                    chunk_text      TEXT NOT NULL,
                    embedding       vector({settings.EMBEDDING_DIM}),
                    created_at      TIMESTAMP DEFAULT NOW()
                );
            """)

            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS excel_rows (
                    id              SERIAL PRIMARY KEY,
                    extraction_id   INT REFERENCES extractions(id) ON DELETE CASCADE,
                    row_index       INT NOT NULL,
                    row_data        JSONB NOT NULL,
                    embedding       vector({settings.EMBEDDING_DIM}),
                    created_at      TIMESTAMP DEFAULT NOW()
                );
            """)

            # New: chat history, scoped per extraction
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id              SERIAL PRIMARY KEY,
                    extraction_id   INT REFERENCES extractions(id) ON DELETE CASCADE,
                    role            TEXT NOT NULL,   -- 'user' | 'assistant'
                    content         TEXT NOT NULL,
                    created_at      TIMESTAMP DEFAULT NOW()
                );
            """)

            conn.commit()
            print("DB initialized.")


# ── extractions ────────────────────────────────────────────

def save_extraction(filename: str, file_type: str, schema: dict, data, raw_text: str = None,
                     status: str = "done") -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO extractions (filename, file_type, schema, data, raw_text, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;
                """,
                (filename, file_type, json.dumps(schema), json.dumps(data), raw_text, status, datetime.utcnow())
            )
            row_id = cur.fetchone()[0]
            conn.commit()
            return row_id


def get_extraction_for_reextract(extraction_id: int):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT file_type, raw_text, data FROM extractions WHERE id = %s;",
                (extraction_id,)
            )
            return cur.fetchone()


def get_all_extractions():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, filename, file_type, schema, data, status, created_at
                FROM extractions ORDER BY created_at DESC;
            """)
            return cur.fetchall()


def get_extraction_by_id(extraction_id: int):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, filename, file_type, schema, data, status, created_at
                FROM extractions WHERE id = %s;
            """, (extraction_id,))
            return cur.fetchone()


# ── PDF chunks ─────────────────────────────────────────────

def save_pdf_chunks(extraction_id: int, chunks: list[str], embeddings: list[list[float]]):
    with get_connection() as conn:
        with conn.cursor() as cur:
            for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                cur.execute(
                    """
                    INSERT INTO pdf_chunks (extraction_id, chunk_index, chunk_text, embedding)
                    VALUES (%s, %s, %s, %s::vector);
                    """,
                    (extraction_id, i, chunk, str(emb))
                )
            conn.commit()


def get_top_pdf_chunks(extraction_id: int, query_embedding: list[float], top_k: int = 3) -> list[str]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT chunk_text
                FROM pdf_chunks
                WHERE extraction_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
                """,
                (extraction_id, str(query_embedding), top_k)
            )
            return [r[0] for r in cur.fetchall()]


# ── Excel rows ─────────────────────────────────────────────

def save_excel_rows(extraction_id: int, rows: list[dict], embeddings: list[list[float]]):
    with get_connection() as conn:
        with conn.cursor() as cur:
            for i, (row, emb) in enumerate(zip(rows, embeddings)):
                cur.execute(
                    """
                    INSERT INTO excel_rows (extraction_id, row_index, row_data, embedding)
                    VALUES (%s, %s, %s, %s::vector);
                    """,
                    (extraction_id, i, json.dumps(row), str(emb))
                )
            conn.commit()


def get_top_excel_rows(extraction_id: int, query_embedding: list[float], top_k: int = 50) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT row_data
                FROM excel_rows
                WHERE extraction_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
                """,
                (extraction_id, str(query_embedding), top_k)
            )
            return [r[0] for r in cur.fetchall()]


# ── Chat messages ──────────────────────────────────────────

def save_chat_message(extraction_id: int, role: str, content: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_messages (extraction_id, role, content, created_at)
                VALUES (%s, %s, %s, %s);
                """,
                (extraction_id, role, content, datetime.utcnow())
            )
            conn.commit()


def get_chat_history(extraction_id: int, limit: int = 20) -> list[dict]:
    """Most recent `limit` messages, returned oldest-first for prompt building."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT role, content, created_at
                FROM chat_messages
                WHERE extraction_id = %s
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (extraction_id, limit)
            )
            rows = cur.fetchall()
            return list(reversed(rows))
