from dataclasses import dataclass, field
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.core.config import get_settings
from src.core.logger import get_logger
from src.ingestion.loader import LoadedDocument

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class Chunk:
    chunk_id: str
    file_name: str
    file_type: str
    text: str
    chunk_index: int
    total_chunks: int
    metadata: dict = field(default_factory=dict)


def chunk_document(doc: LoadedDocument) -> list[Chunk]:
    logger.info(f"Chunking document: {doc.file_name}")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    raw_chunks = splitter.split_text(doc.raw_text)

    if not raw_chunks:
        raise ValueError(f"No chunks produced from {doc.file_name}")

    chunks = [
        Chunk(
            chunk_id=f"{doc.file_name}__chunk_{i}",
            file_name=doc.file_name,
            file_type=doc.file_type,
            text=chunk_text,
            chunk_index=i,
            total_chunks=len(raw_chunks),
            metadata={
                "file_name": doc.file_name,
                "file_type": doc.file_type,
                "chunk_index": i,
                "total_chunks": len(raw_chunks),
            },
        )
        for i, chunk_text in enumerate(raw_chunks)
    ]

    logger.info(f"Produced {len(chunks)} chunks from {doc.file_name}")
    return chunks