from pathlib import Path
from dataclasses import dataclass
from pypdf import PdfReader
from docx import Document as DocxDocument
from ..core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class LoadedDocument:
    file_name: str
    file_type: str
    raw_text: str
    total_pages: int


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}

def load_document(file_path: str | Path) -> LoadedDocument:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {path.suffix}. "
            f"Supported: {SUPPORTED_EXTENSIONS}"
        )

    logger.info(f"Loading file: {path.name} ({path.suffix})")

    match path.suffix.lower():
        case ".pdf":
            return _load_pdf(path)
        case ".docx":
            return _load_docx(path)
        case ".txt":
            return _load_txt(path)


def _load_pdf(path: Path) -> LoadedDocument:
    reader = PdfReader(path)
    pages = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text and text.strip():
            pages.append(text.strip())
        else:
            logger.warning(f"Page {i + 1} of {path.name} has no extractable text")

    raw_text = "\n\n".join(pages)

    if not raw_text.strip():
        raise ValueError(f"No text could be extracted from {path.name}")

    logger.info(f"Loaded PDF: {path.name} — {len(reader.pages)} pages")

    return LoadedDocument(
        file_name=path.name,
        file_type="pdf",
        raw_text=raw_text,
        total_pages=len(reader.pages),
    )


def _load_docx(path: Path) -> LoadedDocument:
    doc = DocxDocument(path)
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    raw_text = "\n\n".join(paragraphs)

    if not raw_text.strip():
        raise ValueError(f"No text could be extracted from {path.name}")

    logger.info(f"Loaded DOCX: {path.name} — {len(paragraphs)} paragraphs")

    return LoadedDocument(
        file_name=path.name,
        file_type="docx",
        raw_text=raw_text,
        total_pages=len(paragraphs),
    )


def _load_txt(path: Path) -> LoadedDocument:
    raw_text = path.read_text(encoding="utf-8").strip()

    if not raw_text:
        raise ValueError(f"File is empty: {path.name}")

    line_count = len(raw_text.splitlines())
    logger.info(f"Loaded TXT: {path.name} — {line_count} lines")

    return LoadedDocument(
        file_name=path.name,
        file_type="txt",
        raw_text=raw_text,
        total_pages=line_count,
    )