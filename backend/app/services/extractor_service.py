from app.utils.pdf_parser import extract_text_from_pdf
from app.utils.excel_parser import extract_json_from_excel
from app.services.llm_service import extract_json, extract_with_custom_schema


def chunk_text(text, max_chars=5000):
    """Keep chunks small enough for the LLM's context window."""
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


def process_file(file_path: str, filename: str):
    filename_lower = filename.lower()
    is_tabular = filename_lower.endswith((".xlsx", ".xls", ".csv"))

    if is_tabular:
        # Bypass LLM entirely — direct structured conversion
        return extract_json_from_excel(file_path)

    elif filename_lower.endswith(".pdf"):
        text = extract_text_from_pdf(file_path)

        if not text.strip():
            return {
                "schema": {"warning": "No text could be extracted from PDF"},
                "data": []
            }

        chunks = chunk_text(text)
        results = []
        schema = None

        # For initial upload: extract schema and data from the initial chunks.
        # Limit initial upload extraction to up to 3 chunks to prevent rate-limit exhaustion.
        # Full retrieval across all chunks is performed via /reextract and /chat using pgvector.
        max_chunks_initial = min(len(chunks), 3)
        for i in range(max_chunks_initial):
            chunk = chunks[i]
            try:
                if not schema:
                    res = extract_json(chunk, is_tabular=False)

                    if isinstance(res, dict) and "error" in res:
                        results.append({"chunk_index": i, "parse_error": res["error"], "raw": res.get("raw_content", "")})
                        continue

                    if isinstance(res, dict) and "input_structure" in res:
                        schema = res["input_structure"]
                        extracted = res.get("extracted_data", [])
                        if isinstance(extracted, list):
                            results.extend(extracted)
                        else:
                            results.append(extracted)
                    else:
                        results.append(res)
                else:
                    extracted = extract_with_custom_schema([chunk], schema)
                    if isinstance(extracted, list):
                        results.extend(extracted)
                    else:
                        results.append(extracted)

            except Exception as e:
                print(f"Chunk {i} error: {e}")
                results.append({"chunk_index": i, "error": str(e)})

        return {
            "schema": schema if schema else {"warning": "No structured schema detected"},
            "data": results
        }

    else:
        raise ValueError(f"Unsupported file type: {filename}")
