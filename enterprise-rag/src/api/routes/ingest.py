import tempfile
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    HTTPException,
)

from src.auth.dependencies import get_current_workspace
from src.core.logger import get_logger
from src.api.models import IngestResponse
from src.db.models import Workspace
from src.ingestion.loader import load_document
from src.ingestion.chunker import chunk_document
from src.ingestion.indexer import index_chunks


logger = get_logger(__name__)

router = APIRouter()


ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
}

MAX_FILE_SIZE_MB = 20


@router.post(
    "/ingest",
    response_model=IngestResponse,
)
async def ingest_document(
    file: UploadFile = File(...),
    workspace: Workspace = Depends(get_current_workspace),
):
    """
    Upload a document.

    Pipeline:
    upload
    → validate
    → temporary file
    → load document
    → create semantic chunks
    → index in Qdrant + BM25
    """

    # ========================================================
    # 1. VALIDATE FILE NAME
    # ========================================================

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file has no filename.",
        )

    # ========================================================
    # 2. VALIDATE FILE EXTENSION
    # ========================================================

    suffix = Path(
        file.filename
    ).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:

        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type: {suffix}. "
                f"Allowed: {ALLOWED_EXTENSIONS}"
            ),
        )

    # ========================================================
    # 3. READ FILE
    # ========================================================

    contents = await file.read()

    # ========================================================
    # 4. VALIDATE FILE SIZE
    # ========================================================

    size_mb = (
        len(contents)
        / (1024 * 1024)
    )

    if size_mb > MAX_FILE_SIZE_MB:

        raise HTTPException(
            status_code=400,
            detail=(
                f"File too large: "
                f"{size_mb:.1f}MB. "
                f"Max allowed: "
                f"{MAX_FILE_SIZE_MB}MB"
            ),
        )

    logger.info(
        f"Received file: "
        f"{file.filename} "
        f"({size_mb:.2f}MB)"
    )

    # ========================================================
    # 5. WRITE UPLOAD TO TEMPORARY FILE
    # ========================================================

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix,
    ) as tmp:

        tmp.write(contents)

        tmp_path = Path(tmp.name)

    try:

        # ====================================================
        # 6. LOAD DOCUMENT
        # ====================================================

        loaded = load_document(
            file_path=tmp_path,
            original_file_name=file.filename,
        )

        logger.info(
            f"Loaded document: "
            f"{loaded.file_name} "
            f"with {len(loaded.blocks)} blocks"
        )

        # ====================================================
        # 7. CREATE FINAL CHUNKS
        # ====================================================

        chunks = chunk_document(
            loaded
        )

        logger.info(
            f"Created {len(chunks)} chunks "
            f"from {file.filename}"
        )

        # ====================================================
        # 8. INDEX CHUNKS
        # ====================================================

        index_chunks(
            chunks,
            workspace_id=str(workspace.id),
        )

        logger.info(
            f"Ingestion complete: "
            f"{file.filename} "
            f"→ {len(chunks)} chunks"
        )

        # ====================================================
        # 9. RETURN RESPONSE
        # ====================================================

        return IngestResponse(
            message=(
                "Document ingested successfully."
            ),
            file_name=file.filename,
            total_chunks=len(chunks),
        )

    except HTTPException:
        raise

    except Exception as e:

        logger.error(
            f"Ingestion failed for "
            f"{file.filename}: {e}",
            exc_info=True,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                f"Ingestion failed: {str(e)}"
            ),
        )

    finally:

        # ====================================================
        # 10. DELETE TEMPORARY FILE
        # ====================================================

        tmp_path.unlink(
            missing_ok=True
        )
