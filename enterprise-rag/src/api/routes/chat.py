from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage, AIMessage

from src.core.logger import get_logger
from src.api.models import ChatRequest, ChatResponse, RetrievedChunkResponse
from src.agent.graph import run_rag

logger = get_logger(__name__)
router = APIRouter()


def _build_history(history: list) -> list:
    """
    Converts ChatMessage list from the API request
    into LangChain BaseMessage objects for LangGraph.
    """
    messages = []
    for msg in history:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content))
    return messages


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Send a query and get a grounded response.
    Pass session_id to maintain multi-turn memory.
    Pass history to provide previous conversation turns.
    """
    logger.info(
        f"[/chat] session={request.session_id} query='{request.query}'"
    )

    try:
        history = _build_history(request.history)

        result = run_rag(
            query=request.query,
            session_id=request.session_id,
            history=history,
        )

        return ChatResponse(
            response=result["response"],
            session_id=request.session_id,
            retrieved_chunks=[
                RetrievedChunkResponse(
                    text=c["text"],
                    score=c["score"],
                    metadata=c["metadata"],
                )
                for c in result["retrieved_chunks"]
            ],
        )

    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")