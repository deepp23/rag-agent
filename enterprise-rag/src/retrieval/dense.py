from dataclasses import dataclass
import google.generativeai as genai
from qdrant_client import QdrantClient
from src.core.config import get_settings
from src.core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

genai.configure(api_key=settings.gemini_api_key)


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    score: float
    metadata: dict


def embed_query(query: str) -> list[float]:
    result = genai.embed_content(
        model=settings.embedding_model,
        content=query,
        task_type="retrieval_query",
    )
    return result["embedding"]


def dense_search(query: str, client: QdrantClient) -> list[RetrievedChunk]:
    logger.info(f"Dense search for: '{query}'")

    query_vector = embed_query(query)

    results = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        limit=settings.dense_top_k,
        with_payload=True,
    )

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