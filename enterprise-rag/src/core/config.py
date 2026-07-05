from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # LLM
    gemini_api_key: str
    gemini_model: str = "gemini-1.5-pro"

    groq_api_key: str
    groq_model: str = "llama-3.1-8b-instant"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "enterprise_rag"

    # Embeddings (now local, no API needed)
    embedding_model: str = "all-MiniLM-L6-v2"   # ← changed
    embedding_dimension: int = 384              # ← new, explained below

    # Reranker
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 64

    # Sparse index
    bm25_index_path: str = "data/bm25_index.pkl"

    # Retrieval
    dense_top_k: int = 20
    sparse_top_k: int = 20
    rerank_top_k: int = 5

    # App
    app_env: str = "development"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()