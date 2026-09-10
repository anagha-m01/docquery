from fastapi import APIRouter, HTTPException

from app.schemas.extraction import ChatRequest, ChatResponse
from app.services import chat_service

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Ask a free-form question about a previously uploaded file."""
    try:
        result = chat_service.ask_question(req.extraction_id, req.question)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@router.get("/chat/{extraction_id}")
async def chat_history(extraction_id: int):
    """Full conversation history for a given extraction."""
    return {"messages": chat_service.get_history(extraction_id)}
