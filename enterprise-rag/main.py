from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.core.logger import get_logger
from src.api.routes.ingest import router as ingest_router
from src.api.routes.conversations import router as conversations_router
from src.api.routes.auth import router as auth_router

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

if settings.app_env == "development":
    cors_origins = ["*"]
else:
    cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1", tags=["Auth"])
app.include_router(ingest_router, prefix="/api/v1", tags=["Ingestion"])
app.include_router(conversations_router, prefix="/api/v1", tags=["Conversations"])


@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "ok",
        "env": settings.app_env,
        "llm": settings.gemini_model,
        "qdrant": settings.qdrant_url,
    }