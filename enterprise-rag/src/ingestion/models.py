from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentBlock:
    block_id: str
    block_type: str
    text: str

    page_number: int | None = None

    # Heading context active when this block appeared
    section_path: list[str] = field(default_factory=list)

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadedDocument:
    file_name: str
    file_type: str
    blocks: list[DocumentBlock]
    total_pages: int


@dataclass
class Chunk:
    chunk_id: str
    file_name: str
    file_type: str
    text: str
    chunk_index: int
    total_chunks: int
    metadata: dict = field(default_factory=dict)