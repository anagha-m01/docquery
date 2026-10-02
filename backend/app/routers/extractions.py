from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_current_user
from app.core.database import (
    get_all_extractions,
    get_extraction_by_id,
    delete_extraction,
    DatabaseError,
)

router = APIRouter(tags=["extractions"])


@router.get("/extractions")
async def list_extractions(current_user: dict = Depends(get_current_user)):
    """Upload history — every extraction THIS user has run, most recent first."""
    try:
        rows = get_all_extractions(current_user["id"])
    except DatabaseError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"extractions": [dict(r) for r in rows]}


@router.get("/extractions/{extraction_id}")
async def get_extraction(extraction_id: int, current_user: dict = Depends(get_current_user)):
    try:
        row = get_extraction_by_id(extraction_id, current_user["id"])
    except DatabaseError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if not row:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return dict(row)


@router.delete("/extractions/{extraction_id}")
async def remove_extraction(extraction_id: int, current_user: dict = Depends(get_current_user)):
    """Deletes an extraction the user owns, along with its chunks/rows/chat
    history (cascaded at the DB level). Returns 404 for anything that
    doesn't exist OR belongs to someone else — ownership is never
    distinguishable from non-existence to the caller."""
    try:
        deleted = delete_extraction(extraction_id, current_user["id"])
    except DatabaseError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return {"deleted": True, "id": extraction_id}
