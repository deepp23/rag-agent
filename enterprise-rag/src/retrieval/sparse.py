from rank_bm25 import BM25Okapi
from src.core.config import get_settings
from src.core.logger import get_logger
from src.retrieval.dense import RetrievedChunk
from src.ingestion.chunker import Chunk

logger = get_logger(__name__)
settings = get_settings()


def build_bm25_index(chunks: list[Chunk]) -> tuple[BM25Okapi, list[Chunk]]:
    """
    Builds a BM25 index from a list of chunks.
    Returns the index and the original chunks (needed for lookup by rank).
    """
    tokenized = [chunk.text.lower().split() for chunk in chunks]
    index = BM25Okapi(tokenized)
    logger.info(f"BM25 index built with {len(chunks)} chunks.")
    return index, chunks


def sparse_search(
    query: str,
    bm25_index: BM25Okapi,
    chunks: list[Chunk],
) -> list[RetrievedChunk]:
    """
    Runs BM25 sparse retrieval against the in-memory index.
    Returns top-k results as RetrievedChunk objects.
    """
    logger.info(f"Sparse search for: '{query}'")

    tokenized_query = query.lower().split()
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