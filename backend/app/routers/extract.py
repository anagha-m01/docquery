import os
import shutil
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.core.config import settings
from app.core.database import save_extraction, save_pdf_chunks, save_excel_rows
from app.services.extractor_service import process_file
from app.services.llm_service import get_chunks
from app.services.embedding_service import embed_batch
from app.utils.pdf_parser import extract_text_from_pdf

router = APIRouter(tags=["extract"])


@router.post("/extract")
async def extract(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        result = process_file(tmp_path, file.filename)
        schema = result.get("schema", {})
        data = result.get("data", result)

        if ext == ".pdf":
            raw_text = extract_text_from_pdf(tmp_path)

            row_id = save_extraction(
                filename=file.filename, file_type=ext.lstrip("."),
                schema=schema, data=data, raw_text=raw_text
            )

            chunks = get_chunks(raw_text)
            embeddings = embed_batch(chunks)
            save_pdf_chunks(row_id, chunks, embeddings)

        else:
            rows = result.get("rows", data)

            row_id = save_extraction(
                filename=file.filename, file_type=ext.lstrip("."),
                schema=schema, data=data
            )

            row_texts = [" | ".join(f"{k}: {v}" for k, v in row.items()) for row in rows]
            embeddings = embed_batch(row_texts)
            save_excel_rows(row_id, rows, embeddings)

        return {"id": row_id, "data": result}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")
    finally:
        os.unlink(tmp_path)
