import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.database import save_extraction, save_pdf_chunks, save_excel_rows, DatabaseError
from app.services.extractor_service import process_file
from app.services.llm_service import get_chunks, LLMServiceError
from app.services.embedding_service import embed_batch, EmbeddingServiceError
from app.utils.pdf_parser import extract_text_from_pdf

router = APIRouter(tags=["extract"])


@router.post("/extract")
async def extract(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file was provided.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )

    # Stream to disk while enforcing the size cap, instead of trusting
    # Content-Length or loading the whole upload into memory first.
    total_bytes = 0
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp_path = tmp.name
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > settings.MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File is too large. Max size is {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                    )
                tmp.write(chunk)

        if total_bytes == 0:
            raise HTTPException(status_code=400, detail="This file is empty — there's nothing to extract.")

        result = process_file(tmp_path, file.filename)
        schema = result.get("schema", {})
        data = result.get("data", result)

        if ext == ".pdf":
            raw_text = extract_text_from_pdf(tmp_path)

            row_id = save_extraction(
                filename=file.filename, file_type=ext.lstrip("."),
                schema=schema, data=data, raw_text=raw_text, user_id=current_user["id"],
            )

            chunks = get_chunks(raw_text)
            if chunks:
                embeddings = embed_batch(chunks)
                save_pdf_chunks(row_id, chunks, embeddings)

        else:
            rows = result.get("rows", data)

            row_id = save_extraction(
                filename=file.filename, file_type=ext.lstrip("."),
                schema=schema, data=data, user_id=current_user["id"],
            )

            if rows:
                row_texts = [" | ".join(f"{k}: {v}" for k, v in row.items()) for row in rows]
                embeddings = embed_batch(row_texts)
                save_excel_rows(row_id, rows, embeddings)

        return {"id": row_id, "data": result}

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (LLMServiceError, EmbeddingServiceError, DatabaseError) as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
            