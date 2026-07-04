from dataclasses import dataclass
from google import genai
from google.genai import types
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, SearchRequest
from src.core.config import get_settings
from src.core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

client_genai = genai.Client(api_key=settings.gemini_api_key)


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    score: float
    metadata: dict


def embed_query(query: str) -> list[float]:
    result = client_genai.models.embed_content(
        model=settings.embedding_model,
        contents=query,
        config=types.EmbedContentConfig(
            task_type="retrieval_query",
        ),
    )
    return result.embeddings[0].values


def dense_search(query: str, client: QdrantClient) -> list[RetrievedChunk]:
    logger.info(f"Dense search for: '{query}'")

    query_vector = embed_query(query)

    results = client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
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