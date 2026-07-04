import pickle
import uuid
from pathlib import Path

from rank_bm25 import BM25Okapi
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import get_settings
from src.core.logger import get_logger
from src.ingestion.chunker import Chunk

logger = get_logger(__name__)
settings = get_settings()

client_genai = genai.Client(api_key=settings.gemini_api_key)

# FIX #2: stable namespace so uuid5 IDs are deterministic per chunk_id
QDRANT_ID_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")

# FIX #8: where the BM25 index gets persisted between runs
BM25_INDEX_PATH = Path(settings.bm25_index_path)

# Simple stopword list for FIX #9 (swap for nltk's if you want it more complete)
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
    "in", "on", "at", "to", "of", "for", "with", "as", "by", "this",
    "that", "it", "be", "from",
}


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url)


def ensure_collection(client: QdrantClient, vector_size: int) -> None:
    existing = [c.name for c in client.get_collections().collections]

    if settings.qdrant_collection not in existing:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        logger.info(f"Created Qdrant collection: {settings.qdrant_collection}")
    else:
        logger.info(f"Collection already exists: {settings.qdrant_collection}")


def _deterministic_point_id(chunk_id: str) -> str:
    """FIX #2: same chunk_id always maps to same point ID, so
    reindexing a document overwrites old vectors instead of
    duplicating them."""
    return str(uuid.uuid5(QDRANT_ID_NAMESPACE, chunk_id))


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
def _embed_batch(texts: list[str]) -> list[list[float]]:
    """FIX #3 + #7: single batched call (matches semantic_chunker's
    pattern) wrapped in retry-with-backoff so a transient API hiccup
    doesn't kill the whole ingestion job."""
    result = client_genai.models.embed_content(
        model=settings.embedding_model,
        contents=texts,
        config=types.EmbedContentConfig(task_type="retrieval_document"),
    )
    return [embedding.values for embedding in result.embeddings]


def embed_texts(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    """FIX #3: batches requests instead of one API call per text.
    Adjust batch_size to your embedding model's documented limit."""
    logger.info(f"Embedding {len(texts)} chunks via Gemini...")

    embeddings: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        embeddings.extend(_embed_batch(batch))

    logger.info("Embedding complete.")
    return embeddings


def _tokenize(text: str) -> list[str]:
    """FIX #9: strips punctuation and drops stopwords instead of a
    naive lowercase+split, so BM25 matches "tiers" against "tiers."
    and doesn't waste weight on filler words."""
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
    tokens = cleaned.lower().split()
    return [t for t in tokens if t not in _STOPWORDS]


def index_chunks(chunks: list[Chunk]) -> BM25Okapi:
    qdrant = get_qdrant_client()
    texts = [c.text for c in chunks]

    # dense indexing
    embeddings = embed_texts(texts)
    ensure_collection(qdrant, vector_size=len(embeddings[0]))

    points = [
        PointStruct(
            id=_deterministic_point_id(chunk.chunk_id),  # FIX #2
            vector=embedding,
            payload={
                **chunk.metadata,
                "text": chunk.text,
                "chunk_id": chunk.chunk_id,
            },
        )
        for chunk, embedding in zip(chunks, embeddings)
    ]

    qdrant.upsert(collection_name=settings.qdrant_collection, points=points)
    logger.info(f"Upserted {len(points)} points into Qdrant.")

    # sparse indexing
    tokenized = [_tokenize(text) for text in texts]  # FIX #9
    bm25_index = BM25Okapi(tokenized)
    logger.info("BM25 index built.")

    _save_bm25_index(bm25_index)  # FIX #8

    return bm25_index


def _save_bm25_index(bm25_index: BM25Okapi) -> None:
    """FIX #8: persist BM25 to disk so it survives process restarts
    instead of vanishing as soon as the ingestion job ends."""
    BM25_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BM25_INDEX_PATH, "wb") as f:
        pickle.dump(bm25_index, f)
    logger.info(f"Saved BM25 index to {BM25_INDEX_PATH}")


def load_bm25_index() -> BM25Okapi | None:
    """Companion loader — call this at startup/query time instead of
    rebuilding BM25 from scratch."""
    if not BM25_INDEX_PATH.exists():
        logger.warning(f"No BM25 index found at {BM25_INDEX_PATH}")
        return None

    with open(BM25_INDEX_PATH, "rb") as f:
        return pickle.load(f)