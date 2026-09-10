from pydantic import BaseModel, Field
from typing import Any


class ReExtractRequest(BaseModel):
    extraction_id: int
    schema_: dict[str, Any] = Field(..., alias="schema")
    filename: str

    model_config = {"populate_by_name": True}

    @property
    def schema(self) -> dict[str, Any]:
        return self.schema_


class ChatRequest(BaseModel):
    extraction_id: int
    question: str


class ChatResponse(BaseModel):
    answer: str
    context_used: list[str]
