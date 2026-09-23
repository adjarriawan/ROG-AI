from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=8000)
    model: str | None = Field(default=None, max_length=100)


class Source(BaseModel):
    filename: str
    page: int | None = None
    chunk_index: int | None = None


class ChatResponse(BaseModel):
    answer: str
    tool_used: str | None = None
    sources: list[Source] = []
    model: str | None = None
    tools_used: list[str] = []
    duration_ms: int | None = None


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


class ModelInfo(BaseModel):
    name: str
    size: int
    supports_tools: bool


class ModelList(BaseModel):
    models: list[ModelInfo]
    current: str


class ServiceHealth(BaseModel):
    status: str
    database: str
    ollama: str
    llm_model: str
    embedding_model: str
    documents: int


class DocumentInfo(BaseModel):
    filename: str
    chunks: int
    uploaded_at: datetime


class SessionInfo(BaseModel):
    session_id: str
    messages: int
    last_message: str
    updated_at: datetime
