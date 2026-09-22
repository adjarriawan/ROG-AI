from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=8000)


class Source(BaseModel):
    filename: str


class ChatResponse(BaseModel):
    answer: str
    tool_used: str | None = None
    sources: list[Source] = []


class UploadResponse(BaseModel):
    filename: str
    status: str
    chunks: int = 0
    kind: str


class ChatMessage(BaseModel):
    role: str
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}
