import uuid
from rank_bm25 import BM25Okapi
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
)
import google.generativeai as genai
from src.core.config import get_settings
from src.core.logger import get_logger
from .chunker import Chunk

logger = get_logger(__name__)
settings = get_settings()

# configure gemini
genai.configure(api_key=settings.gemini_api_key)


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url)


def ensure_collection(client: QdrantClient, vector_size: int) -> None:
    existing = [c.name for c in client.get_collections().collections]

    if settings.qdrant_collection not in existing:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"Created Qdrant collection: {settings.qdrant_collection}")
    else:
        logger.info(f"Collection already exists: {settings.qdrant_collection}")


def embed_texts(texts: list[str]) -> list[list[float]]:
    logger.info(f"Embedding {len(texts)} chunks via Gemini...")

    embeddings = []
    # Gemini embedding API processes one at a time
    for text in texts:
        result = genai.embed_content(
            model=settings.embedding_model,
            content=text,
            task_type="retrieval_document",
        )
        embeddings.append(result["embedding"])

    logger.info("Embedding complete.")
    return embeddings


def index_chunks(chunks: list[Chunk]) -> BM25Okapi:
    """
    Embeds chunks, upserts into Qdrant (dense),
    and returns a BM25 index (sparse) built from the same chunks.
    """
    client = get_qdrant_client()
    texts = [c.text for c in chunks]

    # --- Dense indexing (Qdrant) ---
    embeddings = embed_texts(texts)
    ensure_collection(client, vector_size=len(embeddings[0]))

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload={
                **chunk.metadata,
                "text": chunk.text,
                "chunk_id": chunk.chunk_id,
            },
        )
        for chunk, embedding in zip(chunks, embeddings)
    ]

    client.upsert(
        collection_name=settings.qdrant_collection,
        points=points,
    )
    logger.info(f"Upserted {len(points)} points into Qdrant.")

    # --- Sparse indexing (BM25) ---
    tokenized = [text.lower().split() for text in texts]
    bm25_index = BM25Okapi(tokenized)
    logger.info("BM25 index built.")

    return bm25_index