from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.database import (
    get_extraction_for_reextract, get_top_pdf_chunks, get_top_excel_rows, save_extraction,
)
from app.services.embedding_service import embed
from app.services.llm_service import extract_with_custom_schema
from app.schemas.extraction import ReExtractRequest

router = APIRouter(tags=["reextract"])


@router.post("/reextract")
async def reextract(req: ReExtractRequest):
    row = get_extraction_for_reextract(req.extraction_id)
    if not row:
        raise HTTPException(status_code=404, detail="Extraction not found.")

    file_type = row["file_type"]
    is_tabular = file_type in settings.TABULAR_TYPES

    try:
        schema_text = " | ".join(f"{k}: {v}" for k, v in req.schema.items())
        query_embedding = embed(schema_text)

        if is_tabular:
            top_rows = get_top_excel_rows(req.extraction_id, query_embedding, top_k=settings.TOP_K_EXCEL)
            if not top_rows:
                raise HTTPException(status_code=400, detail="No rows found for this extraction.")

            wanted_keys = list(req.schema.keys())
            result = [{key: record.get(key, None) for key in wanted_keys} for record in top_rows]

        else:
            top_chunks = get_top_pdf_chunks(req.extraction_id, query_embedding, top_k=settings.TOP_K_PDF)
            if not top_chunks:
                raise HTTPException(status_code=400, detail="No chunks found. Re-upload the PDF first.")

            result = extract_with_custom_schema(top_chunks, req.schema)

        new_id = save_extraction(
            filename=req.filename,
            file_type=f"{file_type}-reextract",
            schema=req.schema,
            data=result,
            raw_text=row.get("raw_text"),
        )

        return {"id": new_id, "data": result}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Re-extraction failed: {str(e)}")
