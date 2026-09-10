from fastapi import APIRouter, HTTPException

from app.core.database import get_all_extractions, get_extraction_by_id

router = APIRouter(tags=["extractions"])


@router.get("/extractions")
async def list_extractions():
    """Upload history — every extraction ever run, most recent first."""
    rows = get_all_extractions()
    return {"extractions": [dict(r) for r in rows]}


@router.get("/extractions/{extraction_id}")
async def get_extraction(extraction_id: int):
    row = get_extraction_by_id(extraction_id)
    if not row:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return dict(row)
