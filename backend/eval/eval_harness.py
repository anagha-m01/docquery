"""
eval_harness.py
────────────────
Re-runnable extraction quality scoring, instead of a fresh scratch_verify.py
every time someone asks "is it still good?". Run after any change to
pdf_parser.py / llm_service.py / extractor_service.py:

    python backend/eval/eval_harness.py

Scores FOUR separate things — deliberately not blended into one number,
because a single score would have hidden the TOC-grouping gap we found
(every other dimension passed while that one path stayed untested):

1. chunking    — no silent text loss, no known fact split across chunks
2. schema      — known real headings map to a schema key, not a fallback
3. field_acc   — hand-labeled facts actually come out of extraction
4. grounding   — non-null leaves are traceable to source text, using the
                 REAL validate_grounding logic (not naive substring —
                 that's what caused the false "10 ungrounded" alarm last
                 time: raw PDF text has a real \\n where the LLM's clean
                 output has a space, so plain substring matching fails
                 even though the token-overlap check correctly passes it)

Each run appends one row to eval_history.jsonl so regressions are visible
across commits, not just "pass right now."

Add a new test document: drop a case into eval_cases/ (see
eval_cases/policy_document.json for the shape) and a copy of the PDF next
to it. Nothing else to wire up — run_all() picks up every *.json in that
folder automatically.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Load .env before importing app.core.config
for env_candidate in [Path(__file__).resolve().parents[2] / ".env", Path(__file__).resolve().parents[1] / ".env"]:
    if env_candidate.exists():
        for line in env_candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.utils.pdf_parser import extract_sections_from_pdf, extract_toc_headings
from app.services.extractor_service import (
    group_sections_by_toc,
    merge_chunk_results,
    validate_grounding,
    slugify,
)
from app.services.llm_service import (
    get_chunks,
    generate_document_schema,
    extract_chunk_with_schema,
    route_to_schema_key,
    slugify,
)
from app.services.embedding_service import embed, embed_batch

CASES_DIR = Path(__file__).parent / "eval_cases"
HISTORY_FILE = Path(__file__).parent / "eval_history.jsonl"


# ───────────────────────── scoring functions ─────────────────────────

def score_chunking(sections: list[dict], chunks: list[str], known_facts: list[str]) -> dict:
    total_section_chars = sum(len(s["text"]) for s in sections)
    total_chunk_chars = sum(len(c) for c in chunks)

    split_facts = []
    for fact in known_facts:
        containing = [c for c in chunks if fact.lower() in c.lower()]
        if not containing:
            split_facts.append(fact)  # fact not fully inside any single chunk

    return {
        "no_data_loss": total_chunk_chars >= total_section_chars,
        "total_section_chars": total_section_chars,
        "total_chunk_chars": total_chunk_chars,
        "facts_checked": len(known_facts),
        "facts_split_or_missing": split_facts,
        "pass": total_chunk_chars >= total_section_chars and not split_facts,
    }


def score_schema(schema: dict, known_headings: list[str]) -> dict:
    matched, missed = [], []
    for heading in known_headings:
        key = route_to_schema_key(heading, schema)
        (matched if key else missed).append(heading)
    rate = len(matched) / len(known_headings) if known_headings else 1.0
    return {
        "known_headings_checked": len(known_headings),
        "matched_to_schema_key": matched,
        "fell_back_no_match": missed,
        "match_rate": round(rate, 2),
        "pass": rate >= 0.8,  # tune per corpus; flag rather than hard-fail below this
    }


def score_retrieval(chunks: list[str], schema: dict, known_headings: list[str]) -> dict:
    """
    Mirrors what /reextract actually does -- embed each schema key,
    retrieve top-3 chunks by cosine similarity -- but in-memory against
    the chunks we already have, so this runs without Postgres/Docker.
    Embeddings are normalize_embeddings=True in embedding_service, so
    cosine similarity is just the dot product.

    This is the dimension scratch_verify.py tested that nothing else
    here covers -- without it, deleting scratch_verify.py would mean
    losing retrieval coverage, not just losing a redundant script.
    """
    import numpy as np

    if not chunks or not schema:
        return {"ran": False, "reason": "no chunks or schema"}

    chunk_vecs = np.array(embed_batch(chunks))  # (n_chunks, dim)

    per_key_results = {}
    for key, sub_schema in schema.items():
        query_text = f"{key}: {json.dumps(sub_schema)}"
        q_vec = np.array(embed(query_text))
        sims = chunk_vecs @ q_vec  # cosine similarity (vectors pre-normalized)
        top_idx = np.argsort(-sims)[:3]
        top_chunks = [chunks[i] for i in top_idx]

        # Topical check: does the retrieved chunk's [SECTION: heading] tag
        # itself route back to THIS key? Reuses the real routing logic
        # rather than a separate ad-hoc string check.
        tags = []
        for c in top_chunks:
            m = re.match(r"^\[SECTION:\s*(.+?)\s*\]", c)
            tags.append(m.group(1) if m else None)
        topical_hit = any(t and route_to_schema_key(t, {key: sub_schema}) == key for t in tags)

        per_key_results[key] = {"retrieved_tags": tags, "topical_hit": topical_hit}

    zero_result_keys = [k for k, v in per_key_results.items() if not v["retrieved_tags"]]
    topical_hits = sum(1 for v in per_key_results.values() if v["topical_hit"])
    hit_rate = topical_hits / len(schema) if schema else 0.0

    return {
        "ran": True,
        "keys_checked": len(schema),
        "zero_result_keys": zero_result_keys,
        "topical_hit_rate": round(hit_rate, 2),
        "per_key": per_key_results,
        "pass": not zero_result_keys and hit_rate >= 0.7,
    }


def _fuzzy_contains(haystack_value, needle: str) -> bool:
    """Loose match for field-accuracy scoring: needle's words should
    mostly appear in the stringified extracted value, order-independent,
    so small LLM paraphrasing doesn't count as a miss."""
    hay = json.dumps(haystack_value).lower() if haystack_value is not None else ""
    words = [w for w in re.findall(r"\w+", needle.lower()) if len(w) > 2]
    if not words:
        return needle.lower() in hay
    found = sum(1 for w in words if w in hay)
    return (found / len(words)) >= 0.7


def score_field_accuracy(data: dict, gold_facts: dict[str, str]) -> dict:
    """gold_facts: {"dotted.path.to.field": "expected substring"}"""
    hits, misses = [], []
    for path, expected in gold_facts.items():
        node = data
        for part in path.split("."):
            if isinstance(node, list):
                try:
                    node = node[int(part)]
                except (ValueError, IndexError):
                    node = None
                    break
            elif isinstance(node, dict):
                node = node.get(part)
            else:
                node = None
                break
        (hits if _fuzzy_contains(node, expected) else misses).append(
            {"path": path, "expected": expected, "got": node}
        )
    rate = len(hits) / len(gold_facts) if gold_facts else 1.0
    return {
        "fields_checked": len(gold_facts),
        "hits": len(hits),
        "misses": misses,
        "accuracy": round(rate, 2),
        "pass": rate >= 0.8,
    }


def score_grounding(data: dict, raw_text: str) -> dict:
    """Uses the REAL validate_grounding (exact match OR token-overlap),
    not naive substring — comparing before/after lets us count exactly
    how many leaves it nulled, instead of re-implementing a cruder check
    that produces false alarms."""
    before_leaves = _count_leaves(data)
    grounded = validate_grounding(data, raw_text)
    after_leaves = _count_leaves(grounded)
    nulled = before_leaves - after_leaves
    rate = nulled / before_leaves if before_leaves else 0.0
    return {
        "non_null_leaves_before": before_leaves,
        "non_null_leaves_after": after_leaves,
        "nulled_as_ungrounded": nulled,
        "nulled_rate": round(rate, 3),
        # A HIGH nulled rate on real extraction is itself a signal worth
        # a human look (over-aggressive grounding, or genuine hallucination) —
        # this isn't a simple pass/fail, report the rate and eyeball it.
    }


def _count_leaves(data) -> int:
    if isinstance(data, dict):
        return sum(_count_leaves(v) for v in data.values())
    if isinstance(data, list):
        return sum(_count_leaves(v) for v in data)
    return 0 if data is None else 1


def score_adversarial_injection(chunk_results: list[dict], raw_text: str, schema: dict) -> dict:
    """Plants one fabricated value and confirms the merge pipeline
    rejects it — a grounding check that never nulls anything can't be
    distinguished from a grounding check that was never called."""
    if not chunk_results:
        return {"ran": False}
    import copy
    poisoned = copy.deepcopy(chunk_results)
    FAKE = "Totally Fabricated Eval Sentinel Value XK992"
    # inject into the first string leaf we can find
    def inject(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, str) and v.strip():
                    d[k] = FAKE
                    return True
                if inject(v):
                    return True
        elif isinstance(d, list):
            for item in d:
                if inject(item):
                    return True
        return False
    inject(poisoned[0])

    merged = merge_chunk_results(poisoned, source_text=raw_text, schema=schema)
    rejected = FAKE not in json.dumps(merged)
    return {"ran": True, "fake_value_rejected": rejected, "pass": rejected}


# ───────────────────────── runner ─────────────────────────

def run_case(case_path: Path) -> dict:
    case = json.loads(case_path.read_text())
    pdf_path = case_path.parent / case["pdf_file"]
    if not pdf_path.exists():
        return {"case": case["name"], "error": f"PDF not found: {pdf_path}"}

    t0 = time.perf_counter()
    fine_sections = extract_sections_from_pdf(str(pdf_path))
    toc = extract_toc_headings(str(pdf_path))
    sections = group_sections_by_toc(fine_sections, toc)
    schema = generate_document_schema(sections)
    chunks = get_chunks(sections)

    chunk_results = []
    for i, chunk in enumerate(chunks):
        try:
            res = extract_chunk_with_schema(chunk, schema, chunk_index=i, total_chunks=len(chunks))
            if isinstance(res, dict):
                chunk_results.append(res)
        except Exception as e:
            print(f"  [warn] chunk {i} extraction failed: {e}")

    raw_text = "\n".join(s["text"] for s in sections)
    final_data = merge_chunk_results(chunk_results, source_text=raw_text, schema=schema)
    elapsed = round(time.perf_counter() - t0, 1)

    result = {
        "case": case["name"],
        "toc_found": bool(toc),
        "n_sections": len(sections),
        "n_chunks": len(chunks),
        "elapsed_s": elapsed,
        "chunking": score_chunking(sections, chunks, case.get("known_facts", [])),
        "schema": score_schema(schema, case.get("known_headings", [])),
        "field_accuracy": score_field_accuracy(final_data, case.get("gold_facts", {})),
        "grounding": score_grounding(final_data, raw_text),
        "adversarial": score_adversarial_injection(chunk_results, raw_text, schema),
        "retrieval": score_retrieval(chunks, schema, case.get("known_headings", [])),
    }
    return result


def run_all() -> list[dict]:
    if not CASES_DIR.exists():
        print(f"No eval_cases/ directory at {CASES_DIR} — nothing to run.")
        return []

    results = []
    for case_path in sorted(CASES_DIR.glob("*.json")):
        print(f"\n=== {case_path.stem} ===")
        result = run_case(case_path)
        results.append(result)

        if "error" in result:
            print(f"  ERROR: {result['error']}")
            continue

        c, s, f, g, a = (result["chunking"], result["schema"], result["field_accuracy"],
                          result["grounding"], result["adversarial"])
        r = result["retrieval"]
        print(f"  chunking:   {'PASS' if c['pass'] else 'FAIL'} "
              f"(loss-free: {c['no_data_loss']}, facts split: {len(c['facts_split_or_missing'])})")
        print(f"  schema:     {'PASS' if s['pass'] else 'FLAG'} "
              f"(heading match rate: {s['match_rate']:.0%})")
        print(f"  field_acc:  {'PASS' if f['pass'] else 'FAIL'} "
              f"({f['hits']}/{f['fields_checked']} correct)")
        print(f"  grounding:  nulled {g['nulled_as_ungrounded']}/{g['non_null_leaves_before']} "
              f"leaves ({g['nulled_rate']:.1%}) — eyeball if this jumps between runs")
        print(f"  adversarial:{'PASS' if a.get('pass') else 'FAIL/SKIPPED'} "
              f"(fake value rejected: {a.get('fake_value_rejected')})")
        if r.get("ran"):
            print(f"  retrieval:  {'PASS' if r['pass'] else 'FAIL'} "
                  f"(topical hit rate: {r['topical_hit_rate']:.0%}, "
                  f"zero-result keys: {len(r['zero_result_keys'])})")
            for k, pk in list(r.get("per_key", {}).items())[:8]:
                print(f"    * {k} -> {pk['retrieved_tags']} (topical_hit: {pk['topical_hit']})")
        else:
            print(f"  retrieval:  SKIPPED ({r.get('reason')})")

    HISTORY_FILE.parent.mkdir(exist_ok=True)
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": results}) + "\n")
    print(f"\nAppended to {HISTORY_FILE}")

    return results


if __name__ == "__main__":
    run_all()
    