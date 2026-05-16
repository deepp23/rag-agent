from pydantic import BaseModel, Field


# ── Ingest ──────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    message: str
    file_name: str
    total_chunks: int


# ── Chat ────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(..., min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)


class RetrievedChunkResponse(BaseModel):
    text: str
    score: float
    metadata: dict


class ChatResponse(BaseModel):
    response: str
    session_id: str
    retrieved_chunks: list[RetrievedChunkResponse]