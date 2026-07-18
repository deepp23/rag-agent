from dataclasses import dataclass, field

import numpy as np
from sentence_transformers import SentenceTransformer

from src.core.config import get_settings
from src.core.logger import get_logger
from src.ingestion.models import DocumentBlock

logger = get_logger(__name__)
settings = get_settings()

# Loaded once when this file is first imported, then reused for
# every embedding call — loading the model itself takes a moment,
# but you don't want to reload it on every request.
_embedding_model = SentenceTransformer(settings.embedding_model)

MIN_SIMILARITIES_FOR_PERCENTILE = 5
FALLBACK_THRESHOLD = 0.5


@dataclass
class CandidateUnit:
    text: str
    block_ids: list[str] = field(default_factory=list)
    block_types: list[str] = field(default_factory=list)
    section_path: list[str] = field(default_factory=list)
    page_numbers: list[int] = field(default_factory=list)


def build_candidate_units(blocks: list[DocumentBlock]) -> list[CandidateUnit]:
    units: list[CandidateUnit] = []
    current_list_blocks: list[DocumentBlock] = []

    def flush_list() -> None:
        nonlocal current_list_blocks
        if not current_list_blocks:
            return
        text = "\n".join(f"- {block.text}" for block in current_list_blocks)
        units.append(_blocks_to_unit(current_list_blocks, text=text))
        current_list_blocks = []

    for block in blocks:
        if block.block_type == "list_item":
            current_list_blocks.append(block)
            continue

        flush_list()
        units.append(_blocks_to_unit([block], text=block.text))

    flush_list()
    return units


def _blocks_to_unit(blocks: list[DocumentBlock], text: str) -> CandidateUnit:
    pages = sorted({b.page_number for b in blocks if b.page_number is not None})
    types_ = list(dict.fromkeys(b.block_type for b in blocks))

    section_path = []
    for block in reversed(blocks):
        if block.section_path:
            section_path = block.section_path.copy()
            break

    return CandidateUnit(
        text=text,
        block_ids=[b.block_id for b in blocks],
        block_types=types_,
        section_path=section_path,
        page_numbers=pages,
    )


def embed_units(units: list[CandidateUnit]) -> list[list[float]]:
    if not units:
        return []

    texts = [unit.text for unit in units]

    logger.info(f"Embedding {len(texts)} candidate units (local model)")

    embeddings = _embedding_model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    logger.info("Embedding complete.")

    return embeddings.tolist()


def cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    a = np.asarray(vector_a, dtype=np.float32)
    b = np.asarray(vector_b, dtype=np.float32)

    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    if denominator == 0:
        return 0.0

    return float(np.dot(a, b) / denominator)


def calculate_similarities(embeddings: list[list[float]]) -> list[float]:
    similarities = []
    for index in range(len(embeddings) - 1):
        score = cosine_similarity(embeddings[index], embeddings[index + 1])
        similarities.append(score)
    return similarities


def find_dynamic_threshold(similarities: list[float]) -> float:
    if not similarities:
        return 0.0

    if len(similarities) < MIN_SIMILARITIES_FOR_PERCENTILE:
        logger.info(
            f"Only {len(similarities)} similarity scores — "
            f"using fallback threshold {FALLBACK_THRESHOLD} "
            f"instead of percentile."
        )
        return FALLBACK_THRESHOLD

    values = np.asarray(similarities, dtype=np.float32)
    return float(np.percentile(values, 25))