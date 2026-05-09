from sentence_transformers import CrossEncoder
from src.core.config import get_settings
from src.core.logger import get_logger
from src.retrieval.dense import RetrievedChunk

logger = get_logger(__name__)
settings = get_settings()

# load once at module level — expensive to reload on every request
_reranker: CrossEncoder | None = None


def get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        logger.info(f"Loading reranker model: {settings.reranker_model}")
        _reranker = CrossEncoder(settings.reranker_model)
        logger.info("Reranker model loaded.")
    return _reranker


def rerank(
    query: str,
    chunks: list[RetrievedChunk],
) -> list[RetrievedChunk]:
    """
    Re-scores each (query, chunk) pair using a cross-encoder.
    Much more accurate than bi-encoder similarity alone because
    it sees both query and chunk together at inference time.
    """
    if not chunks:
        logger.warning("Reranker received empty chunk list.")
        return []

    logger.info(f"Reranking {len(chunks)} chunks...")

    reranker = get_reranker()

    # cross-encoder expects list of [query, text] pairs
    pairs = [[query, chunk.text] for chunk in chunks]
    scores = reranker.predict(pairs)

    reranked = sorted(
        zip(chunks, scores),
        key=lambda x: x[1],
        reverse=True,
    )

    top_k = reranked[: settings.rerank_top_k]

    results = [
        RetrievedChunk(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            score=float(score),
            metadata=chunk.metadata,
        )
        for chunk, score in top_k
    ]

    logger.info(f"Reranker kept top {len(results)} chunks.")
    return results