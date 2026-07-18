from rank_bm25 import BM25Okapi
from src.core.config import get_settings
from src.core.logger import get_logger
from src.retrieval.dense import RetrievedChunk
from src.ingestion.chunker import Chunk

logger = get_logger(__name__)
settings = get_settings()

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
    "in", "on", "at", "to", "of", "for", "with", "as", "by", "this",
    "that", "it", "be", "from",
}


def tokenize(text: str) -> list[str]:
    """
    Shared tokenizer used both when the corpus-wide BM25 index is built
    at ingest time and when a query is tokenized at search time — they
    must match or BM25 scores are meaningless.
    """
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
    tokens = cleaned.lower().split()
    return [t for t in tokens if t not in _STOPWORDS]


def sparse_search(
    query: str,
    bm25_index: BM25Okapi,
    chunks: list[Chunk],
) -> list[RetrievedChunk]:
    """
    Runs BM25 sparse retrieval against the persisted, corpus-wide index.
    Returns top-k results as RetrievedChunk objects.
    """
    logger.info(f"Sparse search for: '{query}'")

    tokenized_query = tokenize(query)
    scores = bm25_index.get_scores(tokenized_query)

    # pair each chunk with its BM25 score and sort descending
    scored = sorted(
        zip(chunks, scores),
        key=lambda x: x[1],
        reverse=True,
    )

    top_k = scored[: settings.sparse_top_k]

    results = [
        RetrievedChunk(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            score=float(score),
            metadata=chunk.metadata,
        )
        for chunk, score in top_k
        if score > 0  # ignore zero-score chunks
    ]

    logger.info(f"Sparse search returned {len(results)} results.")
    return results