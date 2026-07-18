from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.orm import Session

from src.agent.graph import run_rag
from src.auth.dependencies import get_current_workspace
from src.core.logger import get_logger
from src.api.models import (
    ChatResponse,
    ConversationResponse,
    MessageRequest,
    MessageResponse,
    RetrievedChunkResponse,
)
from src.db.models import Conversation, Message, Workspace
from src.db.session import get_db

logger = get_logger(__name__)
router = APIRouter()


def _get_owned_conversation(
    conversation_id: UUID, workspace: Workspace, db: Session
) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace.id,
        )
        .first()
    )
    # 404 rather than 403 — don't reveal whether a conversation with this ID
    # exists in another workspace.
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


def _build_history(messages: list[Message]) -> list:
    history = []
    for msg in messages:
        if msg.role == "user":
            history.append(HumanMessage(content=msg.content))
        else:
            history.append(AIMessage(content=msg.content))
    return history


@router.post(
    "/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED
)
def create_conversation(
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    conversation = Conversation(workspace_id=workspace.id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("/conversations", response_model=list[ConversationResponse])
def list_conversations(
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    return (
        db.query(Conversation)
        .filter(Conversation.workspace_id == workspace.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
def get_conversation_messages(
    conversation_id: UUID,
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    conversation = _get_owned_conversation(conversation_id, workspace, db)
    return conversation.messages


@router.post("/conversations/{conversation_id}/messages", response_model=ChatResponse)
def post_conversation_message(
    conversation_id: UUID,
    request: MessageRequest,
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    conversation = _get_owned_conversation(conversation_id, workspace, db)

    logger.info(f"[/conversations/{conversation_id}/messages] query='{request.query}'")

    history = _build_history(conversation.messages)

    result = run_rag(
        query=request.query,
        workspace_id=str(workspace.id),
        conversation_id=str(conversation.id),
        history=history,
    )

    # Persist both turns only after generation succeeds — if run_rag raises,
    # nothing is written and the client can safely retry the same query.
    retrieved_chunks = [
        {"text": c["text"], "score": c["score"], "metadata": c["metadata"]}
        for c in result["retrieved_chunks"]
    ]

    db.add(Message(conversation_id=conversation.id, role="user", content=request.query))
    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=result["response"],
            retrieved_chunks=retrieved_chunks,
        )
    )
    conversation.title = conversation.title or request.query[:255]
    # Explicit bump: if title was already set, reassigning the same value
    # leaves the attribute "clean" in SQLAlchemy's eyes, so the column-level
    # onupdate wouldn't fire on its own — but conversation list ordering
    # depends on this reflecting the latest activity every turn.
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()

    return ChatResponse(
        conversation_id=conversation.id,
        response=result["response"],
        retrieved_chunks=[RetrievedChunkResponse(**c) for c in retrieved_chunks],
    )
