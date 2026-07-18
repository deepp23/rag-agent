from langchain_core.messages import HumanMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from qdrant_client import QdrantClient
from langchain_groq import ChatGroq
from src.core.config import get_settings
from src.core.logger import get_logger
from src.agent.state import RAGState
from src.retrieval.dense import dense_search
from src.retrieval.sparse import sparse_search
from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.reranker import rerank
from src.ingestion.indexer import load_bm25_index, load_bm25_chunks

logger = get_logger(__name__)
settings = get_settings()

# --- clients loaded once at module level ---

_qdrant_client: QdrantClient | None = None
_llm: ChatGoogleGenerativeAI | None = None


def get_qdrant() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(url=settings.qdrant_url)
        logger.info("Qdrant client initialized.")
    return _qdrant_client

def get_llm() -> ChatGroq:
    global _llm
    if _llm is None:
        _llm = ChatGroq(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            temperature=0.2,
        )
        logger.info("Groq LLM initialized.")
    return _llm


# ── Node 1: Retrieve ────────────────────────────────────────────────


def retrieve_node(state: RAGState) -> dict:
    """
    Pulls the latest user query, runs hybrid retrieval
    (dense + sparse → fusion → rerank) and returns
    the top-k chunks to attach to state.
    """
    logger.info(f"[retrieve_node] query: '{state.query}'")

    client = get_qdrant()

    # 1. dense retrieval — Qdrant vector search, scoped to this workspace
    dense_results = dense_search(state.query, client, workspace_id=state.workspace_id)

    # 2. sparse retrieval — against this workspace's BM25 index persisted at
    #    ingest time. Rebuilding this from a Qdrant scroll on every request
    #    was both slow (full reindex per query) and incomplete (scroll
    #    capped at 1000 points), so we load the persisted index from disk
    #    instead.
    bm25_index = load_bm25_index(state.workspace_id)
    if bm25_index is not None:
        bm25_chunks = load_bm25_chunks(state.workspace_id)
        sparse_results = sparse_search(state.query, bm25_index, bm25_chunks)
    else:
        logger.warning(
            f"No BM25 index found for workspace={state.workspace_id} — skipping sparse search."
        )
        sparse_results = []

    # 3. fuse both result lists via RRF
    fused = reciprocal_rank_fusion(dense_results, sparse_results)

    # 4. rerank with cross-encoder
    reranked = rerank(state.query, fused)

    retrieved = [
        {"text": c.text, "score": c.score, "metadata": c.metadata}
        for c in reranked
    ]

    logger.info(f"[retrieve_node] Retrieved {len(retrieved)} final chunks.")
    return {"retrieved_chunks": retrieved}


# ── Node 2: Generate ────────────────────────────────────────────────


def generate_node(state: RAGState) -> dict:
    """
    Builds a grounded prompt from retrieved chunks +
    conversation history, calls Gemini, and returns
    the response as an AIMessage appended to state.
    """
    logger.info("[generate_node] Generating response...")

    llm = get_llm()

    # build context block from retrieved chunks
    context = "\n\n---\n\n".join(
        f"[Chunk {i+1}]\n{chunk['text']}"
        for i, chunk in enumerate(state.retrieved_chunks)
    )

    # build conversation history string for multi-turn awareness
    history = ""
    if len(state.messages) > 1:
        history_lines = []
        for msg in state.messages[:-1]:  # exclude current message
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            history_lines.append(f"{role}: {msg.content}")
        history = "\n".join(history_lines)

    # final grounded prompt
    prompt = f"""
    You are a professional enterprise assistant.

    Answer the user's question using:
    1. The conversation history, when the answer was provided by the user earlier in the conversation.
    2. The document context, for questions about uploaded documents.

    STRICT RULES:

    1. First determine whether the question can be answered from the conversation history.

    2. If the user previously provided the answer in the conversation, answer using that information directly.

    3. For questions about company policies, procedures, rules, documents, or other uploaded content, answer only with information explicitly supported by the document context.

    4. Start directly with the answer.

    5. Never use introductory phrases such as:
       - "Based on the provided context"
       - "According to the documents"
       - "According to the policy"
       - "The context states"
       - "The document mentions"

    6. Never mention or expose:
       - section numbers
       - section names
       - chunk numbers
       - chunk IDs
       - file names
       - retrieval scores
       - metadata
       - source labels

    7. Do not discuss how the answer was found.

    8. Do not make assumptions or invent missing information.

    9. If the answer is unavailable in both the conversation history and the document context, say exactly:
       "I don't have enough information to answer that."

    10. For document questions, missing information does not mean permission.
        If the documents do not say whether something is allowed, do not say it is allowed.

    11. A general rule does not prove a specific case.
        For example, a general reimbursement limit does not prove that a particular expense is reimbursable.

    12. If the documents contain conflicting policy versions, use only the version explicitly identified as current, active, authoritative, or most recent.

    13. Match the response format to the question:
        - Give a short direct answer for simple questions.
        - Use bullets only when they improve clarity.
        - Do not add unnecessary introductions or conclusions.

    Conversation history:
    {history if history else "No previous conversation."}

    Document context:
    {context}

    Current user question:
    {state.query}

    Answer:
    """

    response = llm.invoke(prompt)
    answer = response.content

    logger.info("[generate_node] Response generated.")

    return {
        "response": answer,
        "messages": [AIMessage(content=answer)],
    }