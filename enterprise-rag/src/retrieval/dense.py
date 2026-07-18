from dataclasses import dataclass
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from src.core.config import get_settings
from src.core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

_embedding_model = SentenceTransformer(settings.embedding_model)


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    score: float
    metadata: dict


def embed_query(query: str) -> list[float]:
    embedding = _embedding_model.encode(
        query,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return embedding.tolist()


def dense_search(query: str, client: QdrantClient, workspace_id: str) -> list[RetrievedChunk]:
    logger.info(f"Dense search for: '{query}'")

    query_vector = embed_query(query)

    results = client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        query_filter=Filter(
            must=[FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id))]
        ),
        limit=settings.dense_top_k,
        with_payload=True,
    ).points

    chunks = [
        RetrievedChunk(
            chunk_id=r.payload.get("chunk_id", ""),
            text=r.payload.get("text", ""),
            score=r.score,
            metadata=r.payload,
        )
        for r in results
    ]

    logger.info(f"Dense search returned {len(chunks)} results.")
    return chunks