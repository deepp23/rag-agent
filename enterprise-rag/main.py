from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.core.logger import get_logger
from src.api.routes.ingest import router as ingest_router
from src.api.routes.chat import router as chat_router

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    logger.info(f"Starting Enterprise RAG API [{settings.app_env}]")
    logger.info(f"Qdrant: {settings.qdrant_url}")
    logger.info(f"LLM: {settings.gemini_model}")
    yield
    # shutdown
    logger.info("Shutting down Enterprise RAG API")


app = FastAPI(
    title="Enterprise RAG API",
    description="Hybrid retrieval RAG chatbot with LangGraph memory",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_env == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router, prefix="/api/v1", tags=["Ingestion"])
app.include_router(chat_router, prefix="/api/v1", tags=["Chat"])


@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "ok",
        "env": settings.app_env,
        "llm": settings.gemini_model,
        "qdrant": settings.qdrant_url,
    }