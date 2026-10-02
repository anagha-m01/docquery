import json
import time

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.database import (
    get_extraction_for_reextract, get_top_pdf_chunks, get_top_excel_rows, save_extraction,
    DatabaseError,
)
from app.services.embedding_service import embed, EmbeddingServiceError
from app.services.llm_service import extract_chunk_with_schema, LLMServiceError
from app.services.extractor_service import merge_chunk_results
from app.schemas.extraction import ReExtractRequest

router = APIRouter(tags=["reextract"])


@router.post("/reextract")
async def reextract(req: ReExtractRequest, current_user: dict = Depends(get_current_user)):
    row = get_extraction_for_reextract(req.extraction_id, current_user["id"])
    if not row:
        raise HTTPException(status_code=404, detail="Extraction not found.")

    file_type = row["file_type"]
    is_tabular = file_type in settings.TABULAR_TYPES
    schema = req.schema
    timings: dict[str, float] = {}

    try:
        if is_tabular:
            t0 = time.perf_counter()
            schema_text = " | ".join(f"{k}: {v}" for k, v in schema.items())
            query_embedding = embed(schema_text)
            timings["embedding_s"] = round(time.perf_counter() - t0, 2)

            top_rows = get_top_excel_rows(req.extraction_id, query_embedding, top_k=settings.TOP_K_EXCEL)
            if not top_rows:
                raise HTTPException(status_code=400, detail="No rows found for this extraction.")

            wanted_keys = list(schema.keys())
            result = [{key: record.get(key, None) for key in wanted_keys} for record in top_rows]

        else:
            # One embedding built from the WHOLE schema, then a single
            # top_k=4 pull, could never cover a schema with 15-20+
            # independent sections — it just kept returning the same
            # handful of globally-closest chunks. Instead, embed each
            # top-level schema key on its own and retrieve top-k PER
            # KEY, then route + extract + merge exactly like the initial
            # /extract pipeline does.
            t0 = time.perf_counter()
            per_section_chunks: dict[str, list[str]] = {}
            for key, sub_schema in schema.items():
                query_text = f"{key}: {json.dumps(sub_schema)}"
                query_embedding = embed(query_text)
                chunks = get_top_pdf_chunks(req.extraction_id, query_embedding, top_k=3)
                if chunks:
                    per_section_chunks[key] = chunks
            timings["embedding_and_retrieval_s"] = round(time.perf_counter() - t0, 2)

            all_chunks = [c for chunks in per_section_chunks.values() for c in chunks]
            if not all_chunks:
                raise HTTPException(status_code=400, detail="No chunks found. Re-upload the PDF first.")

            t1 = time.perf_counter()
            chunk_extractions = []
            for i, chunk in enumerate(all_chunks):
                try:
                    res = extract_chunk_with_schema(chunk, schema, chunk_index=i, total_chunks=len(all_chunks))
                    if isinstance(res, dict):
                        chunk_extractions.append(res)
                except Exception as e:
                    print(f"Error re-extracting chunk {i}: {e}")
            timings["extraction_s"] = round(time.perf_counter() - t1, 2)

            t2 = time.perf_counter()
            result = merge_chunk_results(
                chunk_extractions, source_text=row.get("raw_text", ""), schema=schema
            )
            timings["merge_s"] = round(time.perf_counter() - t2, 2)

        timings["total_s"] = round(sum(timings.values()), 2)
        print(f"[reextract] extraction_id={req.extraction_id} timings: {timings}")

        new_id = save_extraction(
            filename=req.filename,
            file_type=f"{file_type}-reextract",
            schema=schema,
            data=result,
            raw_text=row.get("raw_text"),
            user_id=current_user["id"],
        )

        return {"id": new_id, "data": result}

    except HTTPException:
        raise
    except (LLMServiceError, EmbeddingServiceError, DatabaseError) as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Re-extraction failed: {str(e)}")
    