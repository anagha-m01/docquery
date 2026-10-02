import difflib
import re
import time
from typing import Any

from app.utils.pdf_parser import (
    extract_text_from_pdf,
    extract_sections_from_pdf,
    extract_toc_headings,
)
from app.utils.excel_parser import extract_json_from_excel
from app.services.llm_service import (
    generate_document_schema,
    extract_chunk_with_schema,
    get_chunks,
    slugify,
)


def group_sections_by_toc(fine_sections: list[dict], toc_headings: list[str]) -> list[dict]:
    """
    Font-size heading detection is finer-grained than a document's real
    TOC (it'll happily split "Code of Conduct" into "Introduction",
    "Vision and Mission", "Our Core Values", ... as separate headings).
    Left alone, that turns into 30+ schema keys instead of the ~19 real
    policy sections, and — worse — a policy whose TOC entry maps to
    several font-detected sub-headings can end up scattered across
    several schema paths.

    If the document has a literal TOC/index (extract_toc_headings), fold
    every fine-grained section into the nearest TOC heading that precedes
    it, so section boundaries — and therefore schema keys — match the
    document's own table of contents instead of font-size noise.

    Falls back to returning fine_sections unchanged if there's no TOC.
    """
    if not toc_headings:
        return fine_sections

    toc_slugs = [slugify(h) for h in toc_headings]
    grouped: list[dict] = []
    current: dict | None = None
    toc_ptr = -1  # index into toc_slugs of the TOC heading we're currently inside

    for fs in fine_sections:
        fs_slug = slugify(fs["heading"])

        # Does this fine-grained heading match the NEXT unreached TOC
        # entry closely enough to be its start? Only look forward so a
        # heading that repeats later (e.g. "Objectives") can't snap us
        # back to an earlier TOC section.
        matched_new_section = False
        for look_ahead in range(toc_ptr + 1, len(toc_slugs)):
            ratio = difflib.SequenceMatcher(None, fs_slug, toc_slugs[look_ahead]).ratio()
            if fs_slug == toc_slugs[look_ahead] or ratio > 0.82:
                toc_ptr = look_ahead
                current = {"heading": toc_headings[toc_ptr], "text": (fs.get("text") or "") + "\n", "tables": list(fs.get("tables", []))}
                grouped.append(current)
                matched_new_section = True
                break

        if not matched_new_section:
            if current is None:
                current = {"heading": "Front Matter", "text": "", "tables": []}
                grouped.append(current)
            # Sub-heading text folds into the body of its parent TOC
            # section instead of becoming its own schema key.
            current["text"] += fs["heading"] + "\n" + fs["text"] + "\n"
            current["tables"].extend(fs.get("tables", []))

    return [g for g in grouped if g["text"].strip() or g["tables"]]


def is_empty(val: Any) -> bool:
    """Check if value is considered empty or missing."""
    if val is None:
        return True
    if isinstance(val, str):
        s = val.strip().lower()
        return s in ("", "null", "none", "n/a", "na", "unknown", "undefined", "tbd")
    if isinstance(val, (list, dict)) and len(val) == 0:
        return True
    return False


def is_metadata_noise(item: Any) -> bool:
    """Detect if an array element is repeated header/page noise rather than real data."""
    if is_empty(item):
        return True
    if isinstance(item, str):
        s = item.strip().lower()
        if re.match(r"^page\s+\d+(\s+of\s+\d+)?$", s) or s in (
            "confidential",
            "all rights reserved",
            "table of contents",
        ):
            return True
    elif isinstance(item, dict):
        if not item or all(is_empty(v) for v in item.values()):
            return True
        # Dict where values are equal to keys (table header row extracted as data row)
        if all(
            str(k).strip().lower() == str(v).strip().lower()
            for k, v in item.items()
            if not is_empty(v)
        ):
            return True
        # Dict that only contains page metadata
        keys = set(item.keys())
        if keys.issubset(
            {"page", "page_number", "page_num", "section", "doc_name", "document_name"}
        ):
            return True
    return False


def resolve_conflict(val_a: Any, val_b: Any, key: str = "", source_text: str = "") -> Any:
    """
    Validate conflicting non-null scalar values against the source text.
    Returns the value confirmed by the source text.
    """
    if val_a == val_b:
        return val_a

    if not source_text:
        if isinstance(val_a, str) and isinstance(val_b, str):
            return val_a if len(val_a) >= len(val_b) else val_b
        return val_a

    source_lower = source_text.lower()
    str_a = str(val_a).strip().lower()
    str_b = str(val_b).strip().lower()

    # 1. Direct occurrence in source text
    in_source_a = str_a in source_lower if str_a else False
    in_source_b = str_b in source_lower if str_b else False

    if in_source_a and not in_source_b:
        return val_a
    if in_source_b and not in_source_a:
        return val_b

    # 2. Both present in source text: check proximity to field name / key keywords
    key_words = [w.lower() for w in re.split(r"[_\s\-]+", key) if len(w) > 2]
    if key_words and in_source_a and in_source_b:
        def min_distance_to_key(target_str: str) -> float:
            target_pos = [m.start() for m in re.finditer(re.escape(target_str), source_lower)]
            if not target_pos:
                return float("inf")
            min_dist = float("inf")
            for kw in key_words:
                kw_pos = [m.start() for m in re.finditer(re.escape(kw), source_lower)]
                for p_t in target_pos:
                    for p_kw in kw_pos:
                        min_dist = min(min_dist, abs(p_t - p_kw))
            return min_dist

        dist_a = min_distance_to_key(str_a)
        dist_b = min_distance_to_key(str_b)
        if dist_a < dist_b:
            return val_a
        elif dist_b < dist_a:
            return val_b

    # 3. Frequency count in source text
    count_a = source_lower.count(str_a) if str_a else 0
    count_b = source_lower.count(str_b) if str_b else 0
    if count_a > count_b:
        return val_a
    elif count_b > count_a:
        return val_b

    # Fallback: prefer the longer or more complete non-null value
    if isinstance(val_a, str) and isinstance(val_b, str):
        return val_a if len(val_a) >= len(val_b) else val_b
    return val_a


def merge_and_deduplicate_arrays(
    list_a: list, list_b: list, source_text: str = "", sub_schema: Any = None
) -> list:
    """Merge two lists, removing duplicates, repeated metadata, and merging partial objects."""
    combined = (list_a or []) + (list_b or [])
    if not combined:
        return []

    filtered = [x for x in combined if not is_metadata_noise(x)]
    if not filtered:
        return []

    # If items are primitives (string, int, float, bool)
    if not isinstance(filtered[0], dict):
        deduped = []
        seen = set()
        for item in filtered:
            if item is not None and item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped

    # If items are dicts / objects:
    merged_items = []
    common_id_keys = [
        "id",
        "code",
        "name",
        "title",
        "item",
        "item_name",
        "policy_number",
        "coverage_type",
        "type",
    ]

    for item in filtered:
        if not isinstance(item, dict):
            continue

        matched_idx = -1
        item_id_key = next((k for k in common_id_keys if k in item and not is_empty(item[k])), None)

        if item_id_key:
            item_id_val = str(item[item_id_key]).strip().lower()
            for idx, existing in enumerate(merged_items):
                if item_id_key in existing and str(existing[item_id_key]).strip().lower() == item_id_val:
                    matched_idx = idx
                    break

        if matched_idx == -1:
            for idx, existing in enumerate(merged_items):
                if existing == item:
                    matched_idx = idx
                    break
                overlap_keys = set(existing.keys()) & set(item.keys())
                if overlap_keys:
                    conflict = False
                    for k in overlap_keys:
                        e_val = existing.get(k)
                        i_val = item.get(k)
                        if not is_empty(e_val) and not is_empty(i_val) and e_val != i_val:
                            conflict = True
                            break
                    if not conflict:
                        matched_idx = idx
                        break

        if matched_idx != -1:
            merged_items[matched_idx] = merge_two_objects(
                merged_items[matched_idx], item, source_text, sub_schema
            )
        else:
            merged_items.append(item)

    return merged_items


def merge_two_objects(
    obj_a: dict, obj_b: dict, source_text: str = "", schema: dict | None = None
) -> dict:
    """Recursively merges two structured objects."""
    if not isinstance(obj_a, dict):
        return obj_b if isinstance(obj_b, dict) else {}
    if not isinstance(obj_b, dict):
        return obj_a

    merged = {}
    all_keys = list(obj_a.keys()) + [k for k in obj_b.keys() if k not in obj_a]

    for k in all_keys:
        val_a = obj_a.get(k)
        val_b = obj_b.get(k)
        sub_schema = schema.get(k) if isinstance(schema, dict) else None

        empty_a = is_empty(val_a)
        empty_b = is_empty(val_b)

        if empty_a and empty_b:
            if isinstance(sub_schema, dict) and sub_schema.get("type") == "array":
                merged[k] = []
            elif isinstance(sub_schema, dict) and sub_schema.get("type") == "object":
                merged[k] = {}
            else:
                merged[k] = None
        elif empty_a and not empty_b:
            merged[k] = val_b
        elif not empty_a and empty_b:
            merged[k] = val_a
        else:
            # Both non-empty
            if isinstance(val_a, dict) and isinstance(val_b, dict):
                merged[k] = merge_two_objects(val_a, val_b, source_text, sub_schema)
            elif isinstance(val_a, list) and isinstance(val_b, list):
                merged[k] = merge_and_deduplicate_arrays(val_a, val_b, source_text, sub_schema)
            elif isinstance(val_a, list) and not isinstance(val_b, list):
                merged[k] = merge_and_deduplicate_arrays(val_a, [val_b], source_text, sub_schema)
            elif not isinstance(val_a, list) and isinstance(val_b, list):
                merged[k] = merge_and_deduplicate_arrays([val_a], val_b, source_text, sub_schema)
            else:
                merged[k] = resolve_conflict(val_a, val_b, key=k, source_text=source_text)

    return merged


def validate_grounding(data: Any, source_text: str, _is_long_field: bool = False) -> Any:
    """
    Ensures extracted values are present in the source text and not
    hallucinated. Replaces ungrounded / hallucinated values with None.

    Short factual fields (names, numbers, dates) still need a strong
    token-overlap match — that's where a hallucination actually matters.
    Long free-text fields (a vision/mission statement, a paraphrased
    description) are allowed a lower overlap threshold, since faithful
    paraphrasing naturally drops some exact words; the 15+ word length
    itself is evidence it's quoting/paraphrasing a real passage rather
    than being invented outright.
    """
    if not source_text or not isinstance(source_text, str):
        return data

    source_lower = source_text.lower()

    if isinstance(data, dict):
        return {k: validate_grounding(v, source_text) for k, v in data.items()}

    if isinstance(data, list):
        cleaned_list = []
        for item in data:
            v_clean = validate_grounding(item, source_text)
            if v_clean is not None:
                cleaned_list.append(v_clean)
        return cleaned_list

    if isinstance(data, bool) or data is None:
        return data

    if isinstance(data, (int, float)):
        if data in (0, 1):
            return data
        num_str = str(data)
        if num_str.endswith(".0"):
            int_str = num_str[:-2]
            if int_str in source_text or num_str in source_text:
                return data
        elif num_str in source_text:
            return data
        formatted_comma = f"{data:,}"
        if formatted_comma in source_text:
            return data
        return None

    if isinstance(data, str):
        s = data.strip()
        if not s or is_empty(s):
            return None
        if len(s) <= 2:
            return data if s.lower() in source_lower else None

        if s.lower() in source_lower:
            return data

        tokens = [t.lower() for t in re.findall(r"\b\w+\b", s) if len(t) > 2]
        if not tokens:
            return data if s.lower() in source_lower else None

        found_tokens = [t for t in tokens if t in source_lower]
        overlap_ratio = len(found_tokens) / len(tokens)

        # Long text (>= 15 words) gets a lower bar: paraphrasing a real
        # sentence naturally loses word-for-word overlap, and inventing a
        # whole convincing 15+ word sentence from nothing is a much
        # rarer failure mode than a short hallucinated fact. Short
        # fields (a name, a figure, a short phrase) keep the strict 0.5
        # bar since exact grounding matters most there.
        threshold = 0.35 if len(tokens) >= 15 else 0.5
        if overlap_ratio >= threshold:
            return data
        return None

    return data


def enforce_schema_types(data: Any, schema: Any) -> Any:
    """
    Coerces and preserves data types specified in schema (number, boolean, array, object).
    """
    if data is None:
        return None

    expected_type = None
    properties = None
    items_schema = None

    if isinstance(schema, dict):
        expected_type = schema.get("type")
        properties = schema.get("properties")
        items_schema = schema.get("items")
    elif isinstance(schema, str):
        expected_type = schema.lower()

    if expected_type in ("integer", "int"):
        if isinstance(data, int) and not isinstance(data, bool):
            return data
        if isinstance(data, (float, str)):
            try:
                clean = re.sub(r"[^\d.\-]", "", str(data))
                if clean:
                    return int(float(clean))
            except (ValueError, TypeError):
                pass
        return None

    if expected_type in ("number", "float"):
        if isinstance(data, (int, float)) and not isinstance(data, bool):
            return data
        if isinstance(data, str):
            try:
                clean = re.sub(r"[^\d.\-]", "", data)
                if clean:
                    val = float(clean)
                    return int(val) if val.is_integer() else val
            except (ValueError, TypeError):
                pass
        return None

    if expected_type in ("boolean", "bool"):
        if isinstance(data, bool):
            return data
        if isinstance(data, str):
            lower = data.strip().lower()
            if lower in ("true", "yes", "1", "y"):
                return True
            if lower in ("false", "no", "0", "n"):
                return False
        return bool(data)

    if expected_type in ("array", "list"):
        if not isinstance(data, list):
            data = [data] if not is_empty(data) else []
        if items_schema:
            return [enforce_schema_types(item, items_schema) for item in data]
        return data

    if expected_type in ("object", "dict") or isinstance(data, dict):
        if not isinstance(data, dict):
            return {}
        cleaned = {}
        for k, v in data.items():
            sub_s = None
            if properties and isinstance(properties, dict):
                sub_s = properties.get(k)
            elif isinstance(schema, dict):
                sub_s = schema.get(k)
            cleaned[k] = enforce_schema_types(v, sub_s)
        return cleaned

    if expected_type in ("string", "str") and not isinstance(data, (dict, list)):
        return str(data)

    return data


def merge_chunk_results(
    chunk_results: list[dict], source_text: str = "", schema: dict | None = None
) -> dict:
    """
    Intelligently merge multiple chunk extractions into one final JSON object:
    - Keeps non-null values (nulls never overwrite valid data).
    - Merges and deduplicates arrays, removing repeated metadata.
    - Resolves conflicting values by validating against the source text.
    - Prevents hallucinations by checking values against the source text.
    - Preserves correct schema data types.
    """
    if not chunk_results:
        return {}

    merged = {}
    for chunk_dict in chunk_results:
        if isinstance(chunk_dict, dict):
            unwrapped = chunk_dict
            if "extracted_data" in chunk_dict and isinstance(chunk_dict["extracted_data"], dict):
                unwrapped = chunk_dict["extracted_data"]
            elif "data" in chunk_dict and isinstance(chunk_dict["data"], dict):
                unwrapped = chunk_dict["data"]

            merged = merge_two_objects(merged, unwrapped, source_text=source_text, schema=schema)

    # Validate grounding against source text (prevent hallucinations)
    if source_text:
        merged = validate_grounding(merged, source_text)

    # Enforce correct schema data types
    if schema:
        merged = enforce_schema_types(merged, schema)

    return merged


def process_file(file_path: str, filename: str):
    filename_lower = filename.lower()
    is_tabular = filename_lower.endswith((".xlsx", ".xls", ".csv"))

    if is_tabular:
        # Bypass LLM entirely — direct structured conversion
        return extract_json_from_excel(file_path)

    elif filename_lower.endswith(".pdf"):
        timings: dict[str, float] = {}
        t0 = time.perf_counter()

        raw_text = extract_text_from_pdf(file_path)
        if not raw_text.strip():
            return {
                "schema": {"warning": "No text could be extracted from PDF"},
                "data": {},
            }

        fine_sections = extract_sections_from_pdf(file_path)
        toc_headings = extract_toc_headings(file_path)
        sections = group_sections_by_toc(fine_sections, toc_headings)
        timings["sectioning_s"] = round(time.perf_counter() - t0, 2)

        # 1. Generate ONE schema key per section (heading-driven, not a
        #    blind character-window sample) — this is what stops the same
        #    real-world policy from landing under two different schema
        #    paths.
        t1 = time.perf_counter()
        schema = generate_document_schema(sections)
        timings["schema_generation_s"] = round(time.perf_counter() - t1, 2)

        # 2. Chunk within section boundaries and tag each chunk with its
        #    heading, then extract each chunk against ONLY the schema
        #    key(s) that heading routes to.
        t2 = time.perf_counter()
        chunks = get_chunks(sections, max_chars=3000, overlap=200)
        chunk_extractions = []
        for i, chunk in enumerate(chunks):
            try:
                res = extract_chunk_with_schema(chunk, schema, chunk_index=i, total_chunks=len(chunks))
                if isinstance(res, dict):
                    chunk_extractions.append(res)
            except Exception as e:
                print(f"Error extracting chunk {i}: {e}")
        timings["extraction_s"] = round(time.perf_counter() - t2, 2)

        # 3. Merge chunk results into ONE final JSON object
        t3 = time.perf_counter()
        final_data = merge_chunk_results(chunk_extractions, source_text=raw_text, schema=schema)
        timings["merge_s"] = round(time.perf_counter() - t3, 2)
        timings["total_s"] = round(time.perf_counter() - t0, 2)
        print(f"[process_file] {filename} timings: {timings}")

        # Surface source-PDF text corruption (see pdf_parser module
        # docstring) instead of letting it sit silently inside a table
        # cell the LLM extracted faithfully but which is unreliable.
        warnings = []
        for s in sections:
            for t in s.get("tables", []):
                for row in t.get("rows", []):
                    if "_extraction_warning" in row:
                        warnings.append(
                            f"Section \"{s['heading']}\": possible source-PDF text corruption "
                            f"in a table row — verify against the original document."
                        )

        return {
            "schema": schema if schema else {"warning": "No structured schema detected"},
            "data": final_data,       # One final JSON object!
            "raw_text": raw_text,     # so routers/extract.py doesn't re-parse the PDF
            "chunks": chunks,         # section-tagged chunks, reused for embedding storage
            "warnings": warnings,     # e.g. corrupted source-PDF table text, flagged not silently trusted
        }

    else:
        raise ValueError(f"Unsupported file type: {filename}")
    