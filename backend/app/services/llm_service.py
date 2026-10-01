"""
llm_service.py
───────────────
Groq LLM integration.

extract_json()               — first upload, LLM freely invents schema
                                (kept for callers that don't have a
                                heading-aware schema yet).
generate_document_schema()   — NEW SIGNATURE: takes the section list from
                                pdf_parser.extract_sections_from_pdf(),
                                one schema key per heading, instead of
                                sampling arbitrary text stubs.
get_chunks()                 — NEW SIGNATURE: chunks per section instead
                                of blindly across the whole flat text, and
                                tags each chunk with the heading it came
                                from ("[SECTION: <heading>]\\n...") so a
                                later re-extraction pass can still route
                                it correctly without re-parsing the PDF.
extract_chunk_with_schema()  — now routes each chunk to only the matching
                                schema key(s) before prompting, instead of
                                sending the full schema to every chunk.
extract_with_custom_schema() — unchanged; superseded for /reextract by the
                                per-section retrieval in reextract.py, but
                                left in place in case anything else calls it.
answer_chat_question()       — RAG chat over retrieved chunks/rows, or a
                                pandas-computed answer handed in as context.
"""

import difflib
import json
import re
from groq import Groq, GroqError

from app.core.config import settings

client = Groq(api_key=settings.GROQ_API_KEY)

MAX_CHARS = 3000  # safe chunk size for free tier token limits

# Matches the tag get_chunks() stamps on every chunk it produces.
_SECTION_TAG = re.compile(r"^\[SECTION:\s*(.+?)\s*\]\n", re.DOTALL)


class LLMServiceError(Exception):
    """Raised for any LLM-provider failure (network, auth, rate limit, ...)
    so callers can show one friendly message instead of a raw traceback."""


def _chunk_text(text: str, max_chars: int = MAX_CHARS, overlap: int = 200) -> list[str]:
    if max_chars <= overlap:
        overlap = 0
    chunks = []
    step = max_chars - overlap
    for i in range(0, len(text), step):
        chunk = text[i:i + max_chars]
        if chunk:
            chunks.append(chunk)
        if i + max_chars >= len(text):
            break
    return chunks


def _call_llm(prompt: str, max_tokens: int | None = None) -> dict | list:
    """Sends prompt to Groq and parses JSON response."""
    kwargs = {
        "model": settings.LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens or settings.LLM_EXTRACT_MAX_TOKENS,
    }
    if "json" in prompt.lower():
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(**kwargs)
    except GroqError as e:
        print(f"Groq API error: {e}")
        raise LLMServiceError(
            "The AI service is temporarily unavailable. Please try again in a moment."
        ) from e
    except Exception as e:
        print(f"LLM call unexpected error: {e}")
        raise LLMServiceError(
            "Could not reach the AI service. Please check your connection and try again."
        ) from e

    raw_text = response.choices[0].message.content or ""
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', raw_text, re.DOTALL)
    json_str = match.group(1) if match else raw_text.strip()
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {"error": "Failed to parse JSON", "raw_content": raw_text}


def _parse_list(result) -> list:
    """Normalize LLM output to a list."""
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ["data", "extracted_data", "records", "results"]:
            if key in result and isinstance(result[key], list):
                return result[key]
        return [result]
    return [result]


def slugify(heading: str) -> str:
    """'Divyangjan Policy' -> 'divyangjan_policy'."""
    return re.sub(r"[^a-z0-9]+", "_", heading.lower()).strip("_")


def route_to_schema_key(heading: str, schema: dict) -> str | None:
    """
    Exact slug match first; fuzzy fallback for near-misses (schema keys
    the LLM generated won't always exactly match a heading slug, e.g.
    heading "Policy for Canteen Services" vs schema key "canteen_policy").
    Returns None if nothing matches well enough — caller should fall back
    to sending the full schema for that chunk rather than dropping it.
    """
    if not schema:
        return None
    slug = slugify(heading)
    if slug in schema:
        return slug
    match = difflib.get_close_matches(slug, list(schema.keys()), n=1, cutoff=0.55)
    return match[0] if match else None


def get_chunks(sections: list[dict], max_chars: int = MAX_CHARS, overlap: int = 200) -> list[str]:
    """
    Public — used by the /extract router to get chunks for embedding, and
    internally for extraction. Chunks WITHIN each section (never crosses a
    heading boundary) and tags every chunk with its heading, e.g.:

        "[SECTION: Anti-ragging Policy]\\nSt. Paul's College has adopted..."

    The tag is parsed back out by extract_chunk_with_schema() so retrieval
    (pgvector top-k in /reextract or chat) can still route a chunk to the
    right schema slice even though it only has the stored chunk_text, not
    the original section list.
    """
    all_chunks: list[str] = []
    for section in sections:
        heading = section.get("heading", "Document")
        text = section.get("text", "")
        if not text.strip():
            continue
        for piece in _chunk_text(text, max_chars=max_chars, overlap=overlap):
            all_chunks.append(f"[SECTION: {heading}]\n{piece}")
    return all_chunks


def _split_section_tag(chunk: str) -> tuple[str | None, str]:
    """Returns (heading_or_None, body_text_without_tag)."""
    m = _SECTION_TAG.match(chunk)
    if not m:
        return None, chunk
    return m.group(1), chunk[m.end():]


def extract_json(content: str, is_tabular: bool = False) -> dict:
    """Standard extraction — LLM freely invents schema. Kept for tabular
    files and any caller without a pre-built heading-aware schema."""
    if is_tabular:
        prompt = f"""
You are a highly accurate data extraction system.
Convert the provided tabular dataset into a structured JSON array exactly mimicking the table rows.

Return it strictly in this format:
{{
  "data": [
    {{
      "Column_1_Header": "Value 1",
      "Column_2_Header": "Value 2"
    }}
  ]
}}

Rules:
- Dynamically extract exactly the headers provided in the data.
- Return ONLY valid JSON without any markdown formatting or explanations.

Document:
{content}
"""
    else:
        prompt = f"""
You are an expert data architect and extraction system.

Analyze the document below.
First, dynamically invent a highly structured JSON schema representing the logical structure of this document.
Second, extract all relevant information from the document into that structure.

Return ONLY a valid JSON object with no markdown fences:
{{
  "input_structure": {{
       ... dynamically created schema ...
  }},
  "extracted_data": [
       ... extracted records following your schema ...
  ]
}}

Document:
{content}
"""
    return _call_llm(prompt)


def generate_document_schema(sections: list[dict]) -> dict:
    """
    Generates ONE schema object with exactly one top-level key per
    document heading, instead of sampling arbitrary text windows. This is
    what prevents the same real-world section (e.g. "Discipline &
    Grievance Redressal Policy") from ending up as two different schema
    paths — the heading list is the single source of truth for keys.
    """
    if not sections:
        return {"document": {"type": "object"}}

    outline = "\n".join(f"- {s['heading']}" for s in sections)
    # Cap preview length per section so a handful of long sections don't
    # crowd out the schema's visibility into shorter ones.
    previews = "\n\n".join(
        f"### {s['heading']}\n{s['text'][:1000]}" for s in sections
    )

    prompt = f"""
You are an expert data architect and extraction system.

This document has the following sections, in order:
{outline}

Content preview for each section:
{previews}

Task:
Create ONE JSON schema object with exactly one top-level key per section
listed above. Slugify each heading into snake_case for its key
(e.g. "Anti-ragging Policy" -> "anti_ragging_policy"). Do not invent
sections that are not in the list above, do not merge two headings into
one key, and do not split one heading's content across two keys.

Rules:
- Define proper field names with appropriate types (string, number, integer, boolean, array, object).
- For repeating or itemized data (e.g. line items, coverages, committee members, transactions), use an array of objects.
- Do NOT generate fictitious or placeholder data. Generate ONLY the schema.

Return ONLY a valid JSON object in this format:
{{
  "input_structure": {{
       ... one key per heading above ...
  }}
}}
"""
    res = _call_llm(prompt)
    if isinstance(res, dict):
        if "input_structure" in res and isinstance(res["input_structure"], dict):
            return res["input_structure"]
        if "schema" in res and isinstance(res["schema"], dict):
            return res["schema"]
        if res and not any(k in res for k in ("error", "raw_content")):
            return res
    return {"document": {"type": "object"}}


def extract_chunk_with_schema(chunk: str, schema: dict, chunk_index: int = 0, total_chunks: int = 1) -> dict:
    """
    Extract fields present in a document chunk. Routes the chunk to only
    the schema key(s) matching its heading (via the "[SECTION: ...]" tag
    get_chunks() stamped on it) instead of sending the full schema —
    this is what stops a stray phrase from one policy being filed under
    an unrelated field just because the LLM could see every field name
    at once.

    Falls back to the full schema if the chunk has no tag (e.g. it came
    from extract_json's untagged flow) or the heading doesn't match
    anything in the schema closely enough.
    """
    heading, body = _split_section_tag(chunk)
    routed_key = route_to_schema_key(heading, schema) if heading else None
    scoped_schema = {routed_key: schema[routed_key]} if routed_key else schema

    schema_str = json.dumps(scoped_schema, indent=2)
    heading_line = f'This chunk is from the section "{heading}".\n' if heading else ""

    prompt = f"""
You are a precise data extraction system.
{heading_line}Extract all data from this document chunk strictly adhering to the schema provided.
Only fill fields that belong to this chunk's own section — do not use data
from this chunk to fill fields that clearly belong to a different section.

Schema:
{schema_str}

CRITICAL INSTRUCTIONS:
- Return ONE JSON object representing the extracted fields found in this chunk.
- ONLY extract facts and values directly and explicitly stated in the chunk text.
- Do NOT hallucinate, guess, or invent values not present in the document.
- If a field is not found or not mentioned in this chunk, set its value to null.
- Preserve correct data types: numbers must be numeric (int/float), booleans must be true/false, lists must be JSON arrays.
- Do NOT use placeholder text like "N/A", "Unknown", or invented example names.

Document chunk ({chunk_index + 1} of {total_chunks}):
{body}
"""
    res = _call_llm(prompt)
    if isinstance(res, dict):
        if "data" in res and isinstance(res["data"], dict):
            return res["data"]
        if "extracted_data" in res and isinstance(res["extracted_data"], dict):
            return res["extracted_data"]
        return res
    if isinstance(res, list) and res and isinstance(res[0], dict):
        return res[0]
    return {}


def extract_with_custom_schema(relevant_chunks: list[str], schema: dict) -> list:
    """Re-extraction using pre-selected relevant chunks from pgvector.
    Kept for backward compatibility; /reextract now uses per-section
    retrieval + extract_chunk_with_schema()/merge_chunk_results() instead,
    since a single flat list here can't route chunks to the right schema
    slice the way extract_chunk_with_schema() does."""
    schema_str = json.dumps(schema, indent=2)
    all_results = []

    for i, chunk in enumerate(relevant_chunks):
        prompt = f"""
You are a precise data extraction system.

Extract data from the document chunk strictly following this schema.
Do NOT add or remove any fields.

Schema:
{schema_str}

Rules:
- Every record MUST have exactly the keys in the schema.
- Use null if a field cannot be found.
- Return ONLY a valid JSON object in this format:
{{
  "data": [
    ... extracted records following the schema ...
  ]
}}

Document chunk ({i + 1} of {len(relevant_chunks)}):
{chunk}
"""
        try:
            result = _call_llm(prompt)
            parsed = _parse_list(result)
            meaningful = [
                r for r in parsed
                if isinstance(r, dict) and any(v is not None and v != "" for v in r.values())
            ]
            all_results.extend(meaningful)
        except LLMServiceError:
            raise
        except Exception as e:
            all_results.append({"chunk_index": i, "error": str(e)})

    return all_results


def answer_chat_question(question: str, context_snippets: list[str], history: list[dict],
                          extra_instructions: str = "") -> str:
    """
    RAG chat turn: answer a question using the retrieved context (pdf
    chunks or excel rows, or a pandas-computed summary, pre-formatted as
    strings by chat_service), plus recent conversation history for
    follow-up questions.
    """
    context_str = "\n---\n".join(context_snippets) if context_snippets else "(no relevant content found)"

    history_str = ""
    for turn in history:
        role = "User" if turn["role"] == "user" else "Assistant"
        history_str += f"{role}: {turn['content']}\n"

    prompt = f"""
You are a helpful assistant answering questions about a document the user uploaded.
Answer ONLY using the context below. If the answer isn't in the context, say you
don't have enough information — do not make anything up.
{extra_instructions}

Context from the document:
{context_str}

Conversation so far:
{history_str}

User's new question:
{question}

Give a direct, complete answer — don't cut it short if the question calls for a
longer or fuller answer (e.g. a list, a summary of everything, a full table).
Plain text only, no JSON, no markdown fences.
"""
    try:
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=settings.LLM_ANSWER_MAX_TOKENS,
        )
    except GroqError as e:
        print(f"Groq API error in chat: {e}")
        raise LLMServiceError(
            "The AI service is temporarily unavailable. Please try again in a moment."
        ) from e
    except Exception as e:
        print(f"Chat unexpected error: {e}")
        raise LLMServiceError(
            "Could not reach the AI service. Please check your connection and try again."
        ) from e

    return response.choices[0].message.content.strip()
