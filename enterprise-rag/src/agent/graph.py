from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

from src.core.logger import get_logger
from src.agent.state import RAGState
from src.agent.nodes import retrieve_node, generate_node

logger = get_logger(__name__)


def build_graph() -> StateGraph:
    """
    Wires retrieve → generate into a LangGraph pipeline.
    State flows through both nodes and accumulates
    messages for multi-turn memory.
    """
    graph = StateGraph(RAGState)

    # register nodes
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)

    # wire edges
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


# compile once at module level — reused across all requests
rag_graph = build_graph()


def run_rag(
    query: str,
    workspace_id: str,
    conversation_id: str,
    history: list | None = None,
) -> dict:
    """
    Main entry point to run the RAG pipeline.
    Call this from your FastAPI routes.

    Args:
        query:            the user's question
        workspace_id:     workspace to scope retrieval to (multi-tenant isolation)
        conversation_id:  the persisted conversation this turn belongs to
        history:          list of previous BaseMessage objects for this conversation

    Returns:
        dict with 'response' and 'messages'
    """
    logger.info(f"[run_rag] workspace={workspace_id} conversation={conversation_id} query='{query}'")

    # build initial state
    initial_state = RAGState(
        query=query,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        messages=(history or []) + [HumanMessage(content=query)],
    )

    result = rag_graph.invoke(initial_state)

    return {
        "response": result["response"],
        "messages": result["messages"],
        "retrieved_chunks": result["retrieved_chunks"],
    }