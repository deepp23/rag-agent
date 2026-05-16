import tempfile
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException

from src.core.logger import get_logger
from src.api.models import IngestResponse
from src.ingestion.loader import load_document
from src.ingestion.chunker import chunk_document
from src.ingestion.indexer import index_chunks

logger = get_logger(__name__)
router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_FILE_SIZE_MB = 20


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(file: UploadFile = File(...)):
    """
    Upload a document (PDF, DOCX, TXT).
    Parses → chunks → embeds → stores in Qdrant + BM25.
    """

    # validate extension
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Allowed: {ALLOWED_EXTENSIONS}",
        )

    # validate file size
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File too large: {size_mb:.1f}MB. Max allowed: {MAX_FILE_SIZE_MB}MB",
        )

    logger.info(f"Received file: {file.filename} ({size_mb:.2f}MB)")

    # write to a temp file so loader can read it from disk
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(contents)
        tmp_path = Path(tmp.name)

    try:
        # pipeline: load → chunk → index
        loaded = load_document(tmp_path)
        loaded.file_name = file.filename  # restore original name

        chunks = chunk_document(loaded)
        index_chunks(chunks)

        logger.info(f"Ingestion complete: {file.filename} → {len(chunks)} chunks")

        return IngestResponse(
            message="Document ingested successfully.",
            file_name=file.filename,
            total_chunks=len(chunks),
        )

    except Exception as e:
        logger.error(f"Ingestion failed for {file.filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

    finally:
        # always clean up the temp file
        tmp_path.unlink(missing_ok=True)