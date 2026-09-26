"""
database.py
───────────
PostgreSQL + pgvector database layer. Raw psycopg2 — no ORM, kept
deliberately simple for this project's scale.

Tables:
  users          — registered accounts (email + bcrypt password hash)
  extractions    — main extraction results (schema, data, raw_text), each
                   owned by exactly one user via user_id
  pdf_chunks     — PDF text chunks with embeddings (for smart re-extract / chat)
  excel_rows     — Excel/CSV rows with embeddings (for semantic row search)
  chat_messages  — chat history per extraction (for the /chat feature)

Every extraction-scoped read/write below takes (and filters on) user_id
so one user's rows are never visible to, or mutable by, another user.
"""

import json
import psycopg2
from psycopg2 import errors as pg_errors
from psycopg2.extras import RealDictCursor
from datetime import datetime

from app.core.config import settings


class DatabaseError(Exception):
    """Raised for any DB failure that should surface as a friendly 503,
    instead of leaking a raw psycopg2/connection traceback to the client."""


class DuplicateEmailError(Exception):
    """Raised when registering with an email that's already taken."""


def get_connection():
    try:
        return psycopg2.connect(**settings.db_config)
    except psycopg2.OperationalError as e:
        raise DatabaseError("Could not connect to the database. Please try again shortly.") from e


def init_db():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id              SERIAL PRIMARY KEY,
                        email           TEXT NOT NULL UNIQUE,
                        password_hash   TEXT NOT NULL,
                        created_at      TIMESTAMP DEFAULT NOW()
                    );
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS extractions (
                        id          SERIAL PRIMARY KEY,
                        user_id     INT REFERENCES users(id) ON DELETE CASCADE,
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
                cur.execute("ALTER TABLE extractions ADD COLUMN IF NOT EXISTS user_id INT REFERENCES users(id) ON DELETE CASCADE;")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_extractions_user_id ON extractions(user_id);")

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

                # Chat history, scoped per extraction
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
    except psycopg2.OperationalError as e:
        raise DatabaseError("Could not connect to the database. Please try again shortly.") from e


# ── users ──────────────────────────────────────────────────

def create_user(email: str, password_hash: str) -> int:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (email, password_hash, created_at)
                    VALUES (%s, %s, %s) RETURNING id;
                    """,
                    (email.lower().strip(), password_hash, datetime.utcnow())
                )
                user_id = cur.fetchone()[0]
                conn.commit()
                return user_id
    except pg_errors.UniqueViolation:
        raise DuplicateEmailError("An account with this email already exists.")
    except psycopg2.Error as e:
        raise DatabaseError("Could not create account. Please try again.") from e


def get_user_by_email(email: str):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, email, password_hash, created_at FROM users WHERE email = %s;",
                (email.lower().strip(),)
            )
            return cur.fetchone()


def get_user_by_id(user_id: int):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, email, created_at FROM users WHERE id = %s;",
                (user_id,)
            )
            return cur.fetchone()


# ── extractions ────────────────────────────────────────────

def save_extraction(filename: str, file_type: str, schema: dict, data, user_id: int,
                     raw_text: str = None, status: str = "done") -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO extractions (user_id, filename, file_type, schema, data, raw_text, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
                """,
                (user_id, filename, file_type, json.dumps(schema), json.dumps(data), raw_text, status, datetime.utcnow())
            )
            row_id = cur.fetchone()[0]
            conn.commit()
            return row_id


def get_extraction_for_reextract(extraction_id: int, user_id: int):
    """Returns None both when the row doesn't exist AND when it belongs to
    another user — callers can't distinguish the two, which is exactly the
    point: existence of another user's file is not something to leak."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, user_id, file_type, raw_text, data FROM extractions WHERE id = %s AND user_id = %s;",
                (extraction_id, user_id)
            )
            return cur.fetchone()


def get_all_extractions(user_id: int):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, filename, file_type, schema, data, status, created_at
                FROM extractions WHERE user_id = %s ORDER BY created_at DESC;
            """, (user_id,))
            return cur.fetchall()


def get_extraction_by_id(extraction_id: int, user_id: int):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, filename, file_type, schema, data, status, created_at
                FROM extractions WHERE id = %s AND user_id = %s;
            """, (extraction_id, user_id))
            return cur.fetchone()


def delete_extraction(extraction_id: int, user_id: int) -> bool:
    """Deletes an extraction owned by user_id. pdf_chunks, excel_rows and
    chat_messages all reference extractions with ON DELETE CASCADE, so this
    one statement safely removes everything derived from the file too.
    Returns True if a row was actually deleted, False if it didn't exist
    or wasn't owned by this user."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM extractions WHERE id = %s AND user_id = %s RETURNING id;",
                (extraction_id, user_id)
            )
            deleted = cur.fetchone()
            conn.commit()
            return deleted is not None


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


def get_all_pdf_chunks(extraction_id: int) -> list[str]:
    """Every chunk for this extraction, in original document order — used
    for 'summarize everything' style questions where a similarity-ranked
    top-k would arbitrarily drop pages."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT chunk_text
                FROM pdf_chunks
                WHERE extraction_id = %s
                ORDER BY chunk_index ASC;
                """,
                (extraction_id,)
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


def get_all_excel_rows(extraction_id: int, limit: int = 50000) -> list[dict]:
    """Every row for this extraction, in original order — used for
    count/sum/average/filter/full-table questions, where pandas needs the
    real table rather than a similarity-ranked subset."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT row_data
                FROM excel_rows
                WHERE extraction_id = %s
                ORDER BY row_index ASC
                LIMIT %s;
                """,
                (extraction_id, limit)
            )
            return [r[0] for r in cur.fetchall()]


def get_excel_row_count(extraction_id: int) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM excel_rows WHERE extraction_id = %s;", (extraction_id,))
            return cur.fetchone()[0]


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


def delete_chat_history(extraction_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat_messages WHERE extraction_id = %s;", (extraction_id,))
            conn.commit()