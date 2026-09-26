import pytest
from unittest.mock import MagicMock, patch

from app.services.extractor_service import (
    process_file,
    chunk_text,
    is_empty,
    is_metadata_noise,
    resolve_conflict,
    merge_and_deduplicate_arrays,
    merge_two_objects,
    merge_chunk_results,
    validate_grounding,
    enforce_schema_types,
)


# ── 1. Single Final Output Object ─────────────────────────────

def test_single_final_output_json_object(monkeypatch, tmp_path):
    """PDF structured extraction must return ONE final JSON object, not a list of chunks."""
    pdf_path = tmp_path / "test_doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    mock_text = "Policyholder: Alice Smith. Policy Number: POL-001. Premium: $1200."
    monkeypatch.setattr(
        "app.services.extractor_service.extract_text_from_pdf",
        lambda path: mock_text,
    )
    monkeypatch.setattr(
        "app.services.extractor_service.generate_document_schema",
        lambda full_text, chunks: {
            "policyholder": {"type": "string"},
            "policy_number": {"type": "string"},
            "premium": {"type": "number"},
        },
    )
    monkeypatch.setattr(
        "app.services.extractor_service.extract_chunk_with_schema",
        lambda chunk, schema, chunk_index, total_chunks: {
            "policyholder": "Alice Smith",
            "policy_number": "POL-001",
            "premium": 1200,
        },
    )

    result = process_file(str(pdf_path), "test_doc.pdf")

    assert "schema" in result
    assert "data" in result
    assert isinstance(result["data"], dict)
    assert not isinstance(result["data"], list)
    assert result["data"]["policyholder"] == "Alice Smith"
    assert result["data"]["policy_number"] == "POL-001"
    assert result["data"]["premium"] == 1200


# ── 2. Full Document Schema Generation & Long PDFs ─────────────

def test_long_pdf_all_sections_included(monkeypatch, tmp_path):
    """
    Ensure schema is generated across the full document and all chunks
    from beginning to later sections are processed without early cutoff.
    """
    pdf_path = tmp_path / "long_policy.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 long fake")

    # Simulate a long 8-chunk document with content in early, middle, and later sections
    section_texts = [
        f"Section {i}: Key_{i} value is Value_{i}." for i in range(8)
    ]
    full_text = " ".join(section_texts)

    monkeypatch.setattr(
        "app.services.extractor_service.extract_text_from_pdf",
        lambda path: full_text,
    )
    # Force chunks to match our 8 sections
    monkeypatch.setattr(
        "app.services.extractor_service.chunk_text",
        lambda text, max_chars=5000, overlap=300: section_texts,
    )

    schema_called_with = {}

    def mock_generate_schema(full_text, chunks=None):
        schema_called_with["full_text"] = full_text
        schema_called_with["chunks_count"] = len(chunks) if chunks else 0
        # Schema includes fields spanning all sections
        return {f"key_{i}": {"type": "string"} for i in range(8)}

    monkeypatch.setattr(
        "app.services.extractor_service.generate_document_schema",
        mock_generate_schema,
    )

    extracted_chunk_indices = []

    def mock_extract_chunk(chunk, schema, chunk_index, total_chunks):
        extracted_chunk_indices.append(chunk_index)
        return {f"key_{chunk_index}": f"Value_{chunk_index}"}

    monkeypatch.setattr(
        "app.services.extractor_service.extract_chunk_with_schema",
        mock_extract_chunk,
    )

    result = process_file(str(pdf_path), "long_policy.pdf")

    # Verify schema was generated with full document context
    assert schema_called_with["chunks_count"] == 8
    assert "Section 7" in schema_called_with["full_text"]

    # Verify EVERY chunk up to the final section was processed (not capped at 5)
    assert extracted_chunk_indices == [0, 1, 2, 3, 4, 5, 6, 7]

    # Verify later sections are present in the final merged object
    assert result["data"]["key_0"] == "Value_0"
    assert result["data"]["key_4"] == "Value_4"
    assert result["data"]["key_7"] == "Value_7"


# ── 3. Null Merging ───────────────────────────────────────────

def test_null_merging():
    """Non-null values are retained; nulls/empty/placeholders never overwrite valid data."""
    chunk_1 = {
        "policy_holder": "Jane Smith",
        "policy_number": "POL-999",
        "effective_date": None,
        "expiration_date": "",
        "notes": "N/A",
    }
    chunk_2 = {
        "policy_holder": None,
        "policy_number": "null",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "notes": "Annual renewal",
    }

    source_text = "Jane Smith POL-999 2025-01-01 2026-01-01 Annual renewal"
    merged = merge_chunk_results([chunk_1, chunk_2], source_text=source_text)

    assert merged["policy_holder"] == "Jane Smith"
    assert merged["policy_number"] == "POL-999"
    assert merged["effective_date"] == "2025-01-01"
    assert merged["expiration_date"] == "2026-01-01"
    assert merged["notes"] == "Annual renewal"


# ── 4. Duplicate Arrays & Repeated Metadata Removal ───────────

def test_duplicate_arrays_and_metadata_removal():
    """Arrays are merged and deduplicated; repeated metadata and page markers are removed."""
    chunk_1 = {
        "coverages": [
            {"id": "COV-1", "type": "Liability", "limit": 100000},
            {"id": "COV-2", "type": "Collision", "limit": 50000},
        ],
        "tags": ["personal", "auto", "Page 1 of 3"],
    }
    chunk_2 = {
        "coverages": [
            # Exact duplicate of COV-1
            {"id": "COV-1", "type": "Liability", "limit": 100000},
            # Table header noise
            {"id": "id", "type": "type", "limit": "limit"},
            # New item from page 2
            {"id": "COV-3", "type": "Comprehensive", "limit": 50000},
        ],
        "tags": ["auto", "standard", "all rights reserved"],
    }

    source_text = "COV-1 Liability 100000 COV-2 Collision 50000 COV-3 Comprehensive 50000 personal auto standard"
    merged = merge_chunk_results([chunk_1, chunk_2], source_text=source_text)

    # Primitive array: deduplicated and metadata noise filtered out
    assert merged["tags"] == ["personal", "auto", "standard"]

    # Object array: deduplicated, header row filtered out
    cov_ids = [c["id"] for c in merged["coverages"]]
    assert cov_ids == ["COV-1", "COV-2", "COV-3"]
    assert len(merged["coverages"]) == 3


# ── 5. Conflicting Values Validated Against Source Text ────────

def test_conflicting_values_validation_against_source_text():
    """Conflicting values across chunks are resolved by checking against the source text."""
    # Source text explicitly states POL-12345
    source_text = "Official Policy Document. Policy Number: POL-12345. Insured: Alice Walker."

    chunk_a = {"policy_number": "POL-12345"}  # Grounded in source
    chunk_b = {"policy_number": "POL-99999"}  # Conflicting, not in source

    merged = merge_chunk_results([chunk_a, chunk_b], source_text=source_text)
    assert merged["policy_number"] == "POL-12345"

    # Even if order is reversed:
    merged_rev = merge_chunk_results([chunk_b, chunk_a], source_text=source_text)
    assert merged_rev["policy_number"] == "POL-12345"


def test_conflicting_values_proximity_resolution():
    """When both values occur in document, the one closest to the key keyword wins."""
    source_text = (
        "Claim reference CL-555 was closed. "
        "Policy number POL-777 is active for customer."
    )
    val = resolve_conflict("CL-555", "POL-777", key="policy_number", source_text=source_text)
    assert val == "POL-777"


# ── 6. Hallucination Prevention ───────────────────────────────

def test_hallucination_prevention():
    """Values invented by the model and absent from the source text are removed / nullified."""
    source_text = "Contract between Stark Industries and Wayne Enterprises for shipment of widgets."

    hallucinated_data = {
        "company_a": "Stark Industries",
        "company_b": "Wayne Enterprises",
        "item": "widgets",
        "total_amount": 999999,               # Not in text
        "contact_person": "Peter Parker",     # Hallucinated
        "is_expedited": True,
    }

    grounded = validate_grounding(hallucinated_data, source_text)

    assert grounded["company_a"] == "Stark Industries"
    assert grounded["company_b"] == "Wayne Enterprises"
    assert grounded["item"] == "widgets"
    assert grounded["total_amount"] is None
    assert grounded["contact_person"] is None
    assert grounded["is_expedited"] is True


# ── 7. Preserve Correct Schema Data Types ──────────────────────

def test_preserve_schema_data_types():
    """Preserves correct schema data types (integer, float, boolean, array, object)."""
    schema = {
        "properties": {
            "count": {"type": "integer"},
            "price": {"type": "number"},
            "active": {"type": "boolean"},
            "inactive": {"type": "boolean"},
            "items": {"type": "array"},
            "metadata": {"type": "object"},
        }
    }

    raw_extracted = {
        "count": "42",
        "price": "$1,250.75",
        "active": "true",
        "inactive": "no",
        "items": "single_item",
        "metadata": {"source": "pdf"},
    }

    typed = enforce_schema_types(raw_extracted, schema)

    assert typed["count"] == 42
    assert isinstance(typed["count"], int)

    assert typed["price"] == 1250.75
    assert isinstance(typed["price"], float)

    assert typed["active"] is True
    assert typed["inactive"] is False

    assert typed["items"] == ["single_item"]
    assert isinstance(typed["items"], list)

    assert typed["metadata"] == {"source": "pdf"}
    assert isinstance(typed["metadata"], dict)
