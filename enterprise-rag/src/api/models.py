from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ── Ingest ──────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    message: str
    file_name: str
    total_chunks: int


# ── Auth ────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: UUID
    email: str
    workspace_id: UUID
    created_at: datetime


# ── Conversations ───────────────────────────────────────────────────

class ConversationResponse(BaseModel):
    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class RetrievedChunkResponse(BaseModel):
    text: str
    score: float
    metadata: dict


class MessageRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)


class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime


class ChatResponse(BaseModel):
    conversation_id: UUID
    response: str
    retrieved_chunks: list[RetrievedChunkResponse]
