from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_current_user
from app.core.database import DatabaseError
from app.schemas.extraction import ChatRequest, ChatResponse
from app.services import chat_service
from app.services.llm_service import LLMServiceError
from app.services.embedding_service import EmbeddingServiceError

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    """Ask a free-form question about a previously uploaded file.

    Ownership is enforced inside chat_service: it looks the extraction up
    scoped to current_user's id, so asking about someone else's file
    raises the same 404 as asking about a file that doesn't exist.
    """
    try:
        result = chat_service.ask_question(req.extraction_id, req.question, current_user["id"])
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (LLMServiceError, EmbeddingServiceError, DatabaseError) as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@router.get("/chat/{extraction_id}")
async def chat_history(extraction_id: int, current_user: dict = Depends(get_current_user)):
    """Full conversation history for a given extraction — only if it
    belongs to the requesting user."""
    try:
        return {"messages": chat_service.get_history(extraction_id, current_user["id"])}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=503, detail=str(e))
    