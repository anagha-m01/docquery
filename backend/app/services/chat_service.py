"""
chat_service.py
─────────────────
Lets the user ask free-form questions about a previously uploaded file.

Retrieval strategy (this is the part that used to always pull a fixed
TOP_K_CHAT via vector search, regardless of what was actually asked):

  - Tabular files (csv/xlsx/xls):
      * "aggregate" questions (how many / total / sum / average / count /
        filter / list all / summarize everything / ...) load the FULL
        table with pandas and hand the LLM real, computed statistics
        (row count, per-column sums/means/min/max, top value counts) —
        not a similarity-ranked sample that can't add or count rows it
        never saw.
      * everyday lookup questions ("what's Alice's email?") still use a
        fast top-k vector search over rows, just as before.

  - PDF files:
      * "list all / summarize everything / show all" style questions
        pull every chunk (in original page order, capped to a character
        budget) instead of a handful of the closest-matching ones, so
        content on later pages isn't silently dropped.
      * everyday questions still use top-k vector search over chunks.

Every extraction lookup is scoped to the requesting user_id, so a chat
request for someone else's file raises the same "not found" as a file
that doesn't exist at all.
"""

import re

import pandas as pd

from app.core.config import settings
from app.core.database import (
    get_extraction_for_reextract,
    get_top_pdf_chunks,
    get_all_pdf_chunks,
    get_top_excel_rows,
    get_all_excel_rows,
    save_chat_message,
    get_chat_history,
)
from app.services.embedding_service import embed
from app.services.llm_service import answer_chat_question

# Char budget for how much raw context we're willing to hand the LLM in
# one prompt (across snippets), whether that's PDF chunks or table rows.
_CONTEXT_CHAR_BUDGET = 16000

_BROAD_PATTERNS = re.compile(
    r"\b(list all|show all|all records|all rows|all entries|every (row|record|entry)|"
    r"summarize everything|summarise everything|full table|entire (table|document|file)|"
    r"complete list|everything in (this|the)|whole (table|document|dataset))\b",
    re.IGNORECASE,
)

_AGGREGATE_PATTERNS = re.compile(
    r"\b(how many|count of|total|sum of|average|avg|mean of|maximum|minimum|"
    r"highest|lowest|median|filter|group by|percentage|proportion)\b",
    re.IGNORECASE,
)


def _is_broad_question(question: str) -> bool:
    return bool(_BROAD_PATTERNS.search(question))


def _is_aggregate_question(question: str) -> bool:
    return bool(_AGGREGATE_PATTERNS.search(question)) or _is_broad_question(question)


def _dataframe_stats_context(df: pd.DataFrame) -> list[str]:
    """Real, pandas-computed facts about the whole table — not a sample —
    so the LLM can answer count/total/average questions correctly instead
    of guessing from a handful of similarity-ranked rows."""
    snippets = [f"The table has {len(df)} rows and {len(df.columns)} columns: {', '.join(map(str, df.columns))}."]

    numeric_df = df.select_dtypes(include="number")
    for col in numeric_df.columns:
        series = numeric_df[col].dropna()
        if series.empty:
            continue
        snippets.append(
            f"Column '{col}' (numeric, computed over all {len(series)} non-empty values): "
            f"sum={series.sum():.4g}, average={series.mean():.4g}, "
            f"min={series.min():.4g}, max={series.max():.4g}."
        )

    categorical_cols = [c for c in df.columns if c not in numeric_df.columns]
    for col in categorical_cols[:15]:  # avoid a runaway prompt on very wide tables
        counts = df[col].astype(str).value_counts()
        if 0 < len(counts) <= 30:
            top = counts.head(10)
            pairs = ", ".join(f"{idx!r}: {cnt}" for idx, cnt in top.items())
            snippets.append(f"Column '{col}' value counts (top {len(top)} of {len(counts)} distinct): {pairs}.")

    return snippets


def _tabular_context(extraction_id: int, question: str) -> tuple[list[str], str]:
    if _is_aggregate_question(question):
        rows = get_all_excel_rows(extraction_id, limit=settings.MAX_ROWS_FOR_PANDAS)
        if not rows:
            return [], ""

        df = pd.DataFrame(rows)
        snippets = _dataframe_stats_context(df)

        # If the whole table is small enough, include it verbatim so
        # "list all" / "show every row" can be answered exactly.
        full_dump = "\n".join(
            " | ".join(f"{k}: {v}" for k, v in row.items()) for row in rows
        )
        if len(full_dump) <= _CONTEXT_CHAR_BUDGET:
            snippets.append("Full table (every row):\n" + full_dump)
        else:
            sample = rows[:50]
            sample_dump = "\n".join(
                " | ".join(f"{k}: {v}" for k, v in row.items()) for row in sample
            )
            snippets.append(
                f"Sample of the first {len(sample)} of {len(rows)} rows (the statistics "
                f"above were computed over ALL rows, not just this sample):\n{sample_dump}"
            )

        extra_instructions = (
            "The statistics in the context were computed with pandas over the "
            "ENTIRE table, not a sample — treat row counts, sums, and averages "
            "given there as exact and authoritative."
        )
        return snippets, extra_instructions

    # Everyday lookup — fast top-k vector search, as before.
    top_k = settings.TOP_K_CHAT_BROAD if _is_broad_question(question) else settings.TOP_K_CHAT
    query_embedding = embed(question)
    top_rows = get_top_excel_rows(extraction_id, query_embedding, top_k=top_k)
    snippets = [" | ".join(f"{k}: {v}" for k, v in r.items()) for r in top_rows]
    return snippets, ""


def _pdf_context(extraction_id: int, question: str) -> tuple[list[str], str]:
    if _is_broad_question(question):
        chunks = get_all_pdf_chunks(extraction_id)
        total = 0
        capped = []
        for c in chunks:
            if total + len(c) > _CONTEXT_CHAR_BUDGET and capped:
                break
            capped.append(c)
            total += len(c)
        extra = (
            "" if len(capped) == len(chunks) else
            f"Note: only the first {len(capped)} of {len(chunks)} document sections fit in "
            "this context — mention if the answer might be incomplete."
        )
        return capped, extra

    query_embedding = embed(question)
    top_k = settings.TOP_K_CHAT
    return get_top_pdf_chunks(extraction_id, query_embedding, top_k=top_k), ""


def ask_question(extraction_id: int, question: str, user_id: int) -> dict:
    row = get_extraction_for_reextract(extraction_id, user_id)
    if not row:
        raise ValueError("Extraction not found.")

    question = question.strip()
    if not question:
        raise ValueError("Question cannot be empty.")

    file_type = row["file_type"]
    is_tabular = file_type.replace("-reextract", "") in settings.TABULAR_TYPES

    if is_tabular:
        context_snippets, extra_instructions = _tabular_context(extraction_id, question)
    else:
        context_snippets, extra_instructions = _pdf_context(extraction_id, question)

    history = get_chat_history(extraction_id)

    answer = answer_chat_question(question, context_snippets, history, extra_instructions)

    # Persist both turns so the next question has this one as context
    save_chat_message(extraction_id, "user", question)
    save_chat_message(extraction_id, "assistant", answer)

    return {"answer": answer, "context_used": context_snippets}


def get_history(extraction_id: int, user_id: int) -> list[dict]:
    row = get_extraction_for_reextract(extraction_id, user_id)
    if not row:
        raise ValueError("Extraction not found.")
    return get_chat_history(extraction_id, limit=50)
