from typing import Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from dataclasses import dataclass, field


@dataclass
class RAGState:
    """
    The single state object that flows through
    every node in the LangGraph pipeline.

    add_messages is a reducer — it appends new messages
    to the list instead of overwriting it. This is what
    gives us multi-turn memory across conversation turns.
    """

    # full conversation history — never overwritten, only appended
    messages: Annotated[list[BaseMessage], add_messages] = field(
        default_factory=list
    )

    # the current user query extracted from latest message
    query: str = ""

    # chunks retrieved and reranked for this turn
    retrieved_chunks: list[dict] = field(default_factory=list)

    # the final answer for this turn
    response: str = ""

    # which document collection this session is scoped to
    collection: str = "enterprise_rag"

    # session identifier for multi-tenant isolation
    session_id: str = ""