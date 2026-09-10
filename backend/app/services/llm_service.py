"""
llm_service.py
───────────────
Groq LLM integration.

extract_json()               — first upload, LLM freely invents schema
extract_with_custom_schema() — re-extract using top chunks from pgvector
answer_chat_question()       — new: RAG chat over retrieved chunks/rows
"""

import json
import re
from groq import Groq

from app.core.config import settings

client = Groq(api_key=settings.GROQ_API_KEY)

MAX_CHARS = 3000  # safe chunk size for free tier token limits


def _chunk_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


def _call_llm(prompt: str) -> dict | list:
    """Sends prompt to Groq and parses JSON response."""
    kwargs = {
        "model": settings.LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 4096,
    }
    if "json" in prompt.lower():
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
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


def get_chunks(text: str) -> list[str]:
    """Public — used by extractor_service to get chunks for embedding."""
    return _chunk_text(text)


def extract_json(content: str, is_tabular: bool = False) -> dict:
    """Standard extraction — LLM freely invents schema."""
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


def extract_with_custom_schema(relevant_chunks: list[str], schema: dict) -> list:
    """Re-extraction using pre-selected relevant chunks from pgvector."""
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
        except Exception as e:
            all_results.append({"chunk_index": i, "error": str(e)})

    return all_results


def answer_chat_question(question: str, context_snippets: list[str], history: list[dict]) -> str:
    """
    RAG chat turn: answer a question using only the retrieved context
    (pdf chunks or excel rows, pre-formatted as strings by chat_service),
    plus recent conversation history for follow-up questions.
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

Context from the document:
{context_str}

Conversation so far:
{history_str}

User's new question:
{question}

Give a direct, concise answer. Plain text only, no JSON, no markdown fences.
"""
    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=800
    )
    return response.choices[0].message.content.strip()
