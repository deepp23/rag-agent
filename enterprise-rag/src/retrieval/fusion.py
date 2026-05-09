from src.core.logger import get_logger
from src.retrieval.dense import RetrievedChunk

logger = get_logger(__name__)

# RRF constant — 60 is the standard value from the original paper
RRF_K = 60


def reciprocal_rank_fusion(
    dense_results: list[RetrievedChunk],
    sparse_results: list[RetrievedChunk],
) -> list[RetrievedChunk]:
    """
    Merges dense + sparse results using Reciprocal Rank Fusion (RRF).

    RRF score formula:
        score(d) = Σ 1 / (k + rank(d))

    Higher score = more relevant. Works even when scores
    from dense and sparse are on completely different scales.
    """
    logger.info(
        f"Fusing {len(dense_results)} dense + "
        f"{len(sparse_results)} sparse results via RRF."
    )

    rrf_scores: dict[str, float] = {}
    chunk_map: dict[str, RetrievedChunk] = {}

    # score from dense rankings
    for rank, chunk in enumerate(dense_results):
        rrf_scores[chunk.chunk_id] = (
            rrf_scores.get(chunk.chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        )
        chunk_map[chunk.chunk_id] = chunk

    # score from sparse rankings
    for rank, chunk in enumerate(sparse_results):
        rrf_scores[chunk.chunk_id] = (
            rrf_scores.get(chunk.chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        )
        chunk_map[chunk.chunk_id] = chunk

    # sort by combined RRF score descending
    sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)

    fused = [
        RetrievedChunk(
            chunk_id=cid,
            text=chunk_map[cid].text,
            score=rrf_scores[cid],
            metadata=chunk_map[cid].metadata,
        )
        for cid in sorted_ids
    ]

    logger.info(f"Fusion produced {len(fused)} unique results.")
    return fused