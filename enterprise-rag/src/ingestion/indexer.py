import pickle
import uuid
from pathlib import Path

from rank_bm25 import BM25Okapi
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

from src.core.config import get_settings
from src.core.logger import get_logger
from src.ingestion.chunker import Chunk

logger = get_logger(__name__)
settings = get_settings()

_embedding_model = SentenceTransformer(settings.embedding_model)

QDRANT_ID_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")
BM25_INDEX_PATH = Path(settings.bm25_index_path)

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
    return str(uuid.uuid5(QDRANT_ID_NAMESPACE, chunk_id))


def embed_texts(texts: list[str]) -> list[list[float]]:
    logger.info(f"Embedding {len(texts)} chunks (local model)...")

    embeddings = _embedding_model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    logger.info("Embedding complete.")
    return embeddings.tolist()


def _tokenize(text: str) -> list[str]:
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
    tokens = cleaned.lower().split()
    return [t for t in tokens if t not in _STOPWORDS]


def index_chunks(chunks: list[Chunk]) -> BM25Okapi:
    qdrant = get_qdrant_client()
    texts = [c.text for c in chunks]

    embeddings = embed_texts(texts)
    ensure_collection(qdrant, vector_size=len(embeddings[0]))

    points = [
        PointStruct(
            id=_deterministic_point_id(chunk.chunk_id),
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

    tokenized = [_tokenize(text) for text in texts]
    bm25_index = BM25Okapi(tokenized)
    logger.info("BM25 index built.")

    _save_bm25_index(bm25_index)

    return bm25_index


def _save_bm25_index(bm25_index: BM25Okapi) -> None:
    BM25_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BM25_INDEX_PATH, "wb") as f:
        pickle.dump(bm25_index, f)
    logger.info(f"Saved BM25 index to {BM25_INDEX_PATH}")


def load_bm25_index() -> BM25Okapi | None:
    if not BM25_INDEX_PATH.exists():
        logger.warning(f"No BM25 index found at {BM25_INDEX_PATH}")
        return None

    with open(BM25_INDEX_PATH, "rb") as f:
        return pickle.load(f)