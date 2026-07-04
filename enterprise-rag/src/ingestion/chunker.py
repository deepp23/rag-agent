from src.core.config import get_settings
from src.core.logger import get_logger

from src.ingestion.cleaner import clean_blocks
from src.ingestion.models import Chunk, LoadedDocument

from src.ingestion.semantic_chunker import (
    CandidateUnit,
    build_candidate_units,
    calculate_similarities,
    embed_units,
    find_dynamic_threshold,
)

logger = get_logger(__name__)
settings = get_settings()


def chunk_document(doc: LoadedDocument) -> list[Chunk]:
    logger.info(f"Chunking document: {doc.file_name}")

    cleaned_blocks = clean_blocks(doc.blocks)
    if not cleaned_blocks:
        raise ValueError(f"No usable blocks after cleaning {doc.file_name}")

    logger.info(
        f"Cleaning complete: {len(doc.blocks)} → {len(cleaned_blocks)} blocks"
    )

    units = build_candidate_units(cleaned_blocks)
    if not units:
        raise ValueError(f"No candidate units created for {doc.file_name}")

    logger.info(f"Created {len(units)} candidate units")

    if len(units) == 1:
        assembled = [_finalize_units([units[0]])]
    else:
        embeddings = embed_units(units)
        similarities = calculate_similarities(embeddings)
        threshold = find_dynamic_threshold(similarities)

        logger.info(f"Semantic boundary threshold: {threshold:.4f}")

        assembled = _assemble_chunks(
            units=units,
            similarities=similarities,
            threshold=threshold,
        )

    total_chunks = len(assembled)
    final_chunks: list[Chunk] = []

    for index, item in enumerate(assembled):
        chunk_id = f"{doc.file_name}__chunk_{index}"

        final_chunks.append(
            Chunk(
                chunk_id=chunk_id,
                file_name=doc.file_name,
                file_type=doc.file_type,
                text=item["text"],
                chunk_index=index,
                total_chunks=total_chunks,
                metadata={
                    "chunk_id": chunk_id,
                    "file_name": doc.file_name,
                    "file_type": doc.file_type,
                    "chunk_index": index,
                    "total_chunks": total_chunks,
                    "section_path": item["section_path"],
                    "page_numbers": item["page_numbers"],
                    "block_types": item["block_types"],
                    "source_block_ids": item["block_ids"],
                },
            )
        )

    logger.info(f"Produced {total_chunks} final chunks from {doc.file_name}")
    return final_chunks


def _assemble_chunks(
    units: list[CandidateUnit],
    similarities: list[float],
    threshold: float,
) -> list[dict]:
    chunks: list[dict] = []
    current_units = [units[0]]

    for index in range(1, len(units)):
        previous_unit = units[index - 1]
        current_unit = units[index]
        similarity = similarities[index - 1]

        current_text = _combine_unit_text(current_units)
        proposed_text = current_text + "\n\n" + current_unit.text

        exceeds_max_size = len(proposed_text) > settings.chunk_size
        semantic_break = similarity < threshold
        strong_structure_break = _is_strong_structure_break(
            previous=previous_unit, current=current_unit
        )

        should_split = exceeds_max_size or (
            semantic_break and strong_structure_break
        )

        logger.debug(
            f"Boundary {index - 1} → {index}: "
            f"similarity={similarity:.4f}, "
            f"semantic_break={semantic_break}, "
            f"structure_break={strong_structure_break}, "
            f"size_break={exceeds_max_size}, split={should_split}"
        )

        if should_split:
            chunks.append(_finalize_units(current_units))

            # FIX #4: seed the new chunk with the last unit of the
            # previous chunk (if it wasn't a size-triggered split) so
            # context isn't lost right at the cut point. Skip overlap
            # on size-triggered splits to avoid immediately re-exceeding
            # the size limit.
            if not exceeds_max_size and len(current_units) > 0:
                overlap_unit = current_units[-1]
                current_units = [overlap_unit, current_unit]
            else:
                current_units = [current_unit]
        else:
            current_units.append(current_unit)

    if current_units:
        chunks.append(_finalize_units(current_units))

    return chunks


def _is_strong_structure_break(
    previous: CandidateUnit, current: CandidateUnit
) -> bool:
    if (
        previous.section_path
        and current.section_path
        and previous.section_path != current.section_path
    ):
        return True
    return False


def _combine_unit_text(units: list[CandidateUnit]) -> str:
    return "\n\n".join(unit.text for unit in units)


def _finalize_units(units: list[CandidateUnit]) -> dict:
    section_path: list[str] = []
    for unit in units:
        if unit.section_path:
            section_path = unit.section_path.copy()
            break

    content = _combine_unit_text(units)

    if section_path:
        context = " > ".join(section_path)
        text = f"Section context: {context}\n\n{content}"
    else:
        text = content

    page_numbers = sorted({p for unit in units for p in unit.page_numbers})
    block_types = list(
        dict.fromkeys(bt for unit in units for bt in unit.block_types)
    )
    block_ids = [bid for unit in units for bid in unit.block_ids]

    return {
        "text": text,
        "section_path": section_path,
        "page_numbers": page_numbers,
        "block_types": block_types,
        "block_ids": block_ids,
    }