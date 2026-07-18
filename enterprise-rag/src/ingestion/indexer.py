import pickle
import uuid
from pathlib import Path

from rank_bm25 import BM25Okapi
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PayloadSchemaType
from sentence_transformers import SentenceTransformer

from src.core.config import get_settings
from src.core.logger import get_logger
from src.ingestion.chunker import Chunk
from src.retrieval.sparse import tokenize

logger = get_logger(__name__)
settings = get_settings()

_embedding_model = SentenceTransformer(settings.embedding_model)

QDRANT_ID_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")
BM25_DIR = Path(settings.bm25_dir)


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

        # Needed for efficient workspace-scoped filtering at query time —
        # without it, every filtered search does a full collection scan.
        client.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name="workspace_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        logger.info("Created payload index on workspace_id.")
    else:
        logger.info(f"Collection already exists: {settings.qdrant_collection}")


def _deterministic_point_id(workspace_id: str, chunk_id: str) -> str:
    # Point IDs are unique across the whole (shared) Qdrant collection, so
    # workspace_id must be part of the hash input — otherwise two different
    # workspaces uploading a same-named file (e.g. both "policy.pdf") would
    # compute the same point ID and the second upsert would silently
    # overwrite the first workspace's chunk.
    return str(uuid.uuid5(QDRANT_ID_NAMESPACE, f"{workspace_id}::{chunk_id}"))


def embed_texts(texts: list[str]) -> list[list[float]]:
    logger.info(f"Embedding {len(texts)} chunks (local model)...")

    embeddings = _embedding_model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    logger.info("Embedding complete.")
    return embeddings.tolist()


def index_chunks(chunks: list[Chunk], workspace_id: str) -> BM25Okapi:
    qdrant = get_qdrant_client()
    texts = [c.text for c in chunks]

    embeddings = embed_texts(texts)
    ensure_collection(qdrant, vector_size=len(embeddings[0]))

    points = [
        PointStruct(
            id=_deterministic_point_id(workspace_id, chunk.chunk_id),
            vector=embedding,
            payload={
                **chunk.metadata,
                "text": chunk.text,
                "chunk_id": chunk.chunk_id,
                "workspace_id": workspace_id,
            },
        )
        for chunk, embedding in zip(chunks, embeddings)
    ]

    qdrant.upsert(collection_name=settings.qdrant_collection, points=points)
    logger.info(f"Upserted {len(points)} points into Qdrant (workspace={workspace_id}).")

    # BM25 is a per-workspace, corpus-wide index, so merge these chunks into
    # whatever was already persisted for this workspace rather than
    # overwriting it (otherwise sparse search would only ever cover the most
    # recently ingested file). Re-ingesting the same chunk_id within the same
    # workspace replaces that entry.
    merged_chunks = {c.chunk_id: c for c in _load_bm25_chunks(workspace_id)}
    for chunk in chunks:
        merged_chunks[chunk.chunk_id] = chunk
    all_chunks = list(merged_chunks.values())

    tokenized = [tokenize(c.text) for c in all_chunks]
    bm25_index = BM25Okapi(tokenized)
    logger.info(
        f"BM25 index built over {len(all_chunks)} chunks (workspace={workspace_id})."
    )

    _save_bm25_index(bm25_index, workspace_id)
    _save_bm25_chunks(all_chunks, workspace_id)

    return bm25_index


def _bm25_index_path(workspace_id: str) -> Path:
    return BM25_DIR / workspace_id / "index.pkl"


def _bm25_chunks_path(workspace_id: str) -> Path:
    return BM25_DIR / workspace_id / "chunks.pkl"


def _save_bm25_index(bm25_index: BM25Okapi, workspace_id: str) -> None:
    path = _bm25_index_path(workspace_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(bm25_index, f)
    logger.info(f"Saved BM25 index to {path}")


def load_bm25_index(workspace_id: str) -> BM25Okapi | None:
    path = _bm25_index_path(workspace_id)
    if not path.exists():
        logger.warning(f"No BM25 index found at {path}")
        return None

    with open(path, "rb") as f:
        return pickle.load(f)


def _save_bm25_chunks(chunks: list[Chunk], workspace_id: str) -> None:
    path = _bm25_chunks_path(workspace_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(chunks, f)
    logger.info(f"Saved {len(chunks)} BM25 chunk records to {path}")


def _load_bm25_chunks(workspace_id: str) -> list[Chunk]:
    path = _bm25_chunks_path(workspace_id)
    if not path.exists():
        return []

    with open(path, "rb") as f:
        return pickle.load(f)


def load_bm25_chunks(workspace_id: str) -> list[Chunk]:
    return _load_bm25_chunks(workspace_id)
