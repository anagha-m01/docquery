from pydantic import BaseModel, Field, field_validator
from typing import Any


class ReExtractRequest(BaseModel):
    extraction_id: int
    schema_: dict[str, Any] = Field(..., alias="schema")
    filename: str

    model_config = {"populate_by_name": True}

    @property
    def schema(self) -> dict[str, Any]:
        return self.schema_

    @field_validator("schema_")
    @classmethod
    def schema_must_not_be_empty(cls, v):
        if not v:
            raise ValueError("Schema cannot be empty.")
        return v


class ChatRequest(BaseModel):
    extraction_id: int
    question: str = Field(..., min_length=1)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, v):
        stripped = v.strip()
        if not stripped:
            raise ValueError("Question cannot be empty.")
        return stripped


class ChatResponse(BaseModel):
    answer: str
    context_used: list[str]
    