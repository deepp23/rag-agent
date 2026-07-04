from dataclasses import dataclass, field
import time
import numpy as np

from google import genai
from google.genai import types

from src.core.config import get_settings
from src.core.logger import get_logger
from src.ingestion.models import DocumentBlock
from tenacity import retry, stop_after_attempt, wait_exponential

logger = get_logger(__name__)
settings = get_settings()

client_genai = genai.Client(api_key=settings.gemini_api_key)

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


@retry(
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=2, min=5, max=90),
)
def _embed_batch(texts: list[str]) -> list[list[float]]:
    result = client_genai.models.embed_content(
        model=settings.embedding_model,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type="retrieval_document",
        ),
    )
    return [embedding.values for embedding in result.embeddings]


def embed_units(
    units: list[CandidateUnit],
    batch_size: int = 100,
    delay_between_batches: float = 2.0,
) -> list[list[float]]:

    if not units:
        return []

    texts = [unit.text for unit in units]

    logger.info(f"Embedding {len(texts)} candidate units")

    embeddings: list[list[float]] = []
    total_batches = (len(texts) + batch_size - 1) // batch_size

    for batch_number, start in enumerate(
        range(0, len(texts), batch_size), start=1
    ):
        batch = texts[start : start + batch_size]

        logger.info(f"Embedding batch {batch_number}/{total_batches}")

        embeddings.extend(_embed_batch(batch))

        # Pause between batches (but not after the last one) to
        # stay under the per-minute quota proactively, rather than
        # only reacting once we've already been rejected.
        if batch_number < total_batches:
            time.sleep(delay_between_batches)

    return embeddings


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

    # FIX #5: percentile on a tiny sample is noisy/meaningless.
    # Use a fixed conservative threshold instead when we don't have
    # enough data points to trust a distribution-based cut.
    if len(similarities) < MIN_SIMILARITIES_FOR_PERCENTILE:
        logger.info(
            f"Only {len(similarities)} similarity scores — "
            f"using fallback threshold {FALLBACK_THRESHOLD} "
            f"instead of percentile."
        )
        return FALLBACK_THRESHOLD

    values = np.asarray(similarities, dtype=np.float32)
    return float(np.percentile(values, 25))