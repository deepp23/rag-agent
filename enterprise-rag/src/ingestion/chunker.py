from src.core.config import get_settings
from src.core.logger import get_logger

from src.ingestion.cleaner import clean_blocks

from src.ingestion.models import (
    Chunk,
    LoadedDocument,
)

from src.ingestion.semantic_chunker import (
    CandidateUnit,
    build_candidate_units,
    calculate_similarities,
    embed_units,
    find_dynamic_threshold,
)


logger = get_logger(__name__)
settings = get_settings()


def chunk_document(
    doc: LoadedDocument,
) -> list[Chunk]:
    """
    Main chunking pipeline.

    LoadedDocument
        ↓
    Clean blocks
        ↓
    Build candidate units
        ↓
    Embed candidate units
        ↓
    Compare adjacent units
        ↓
    Detect semantic boundaries
        ↓
    Assemble final chunks
        ↓
    Return Chunk objects
    """

    logger.info(
        f"Chunking document: {doc.file_name}"
    )

    # ========================================================
    # 1. CLEAN DOCUMENT BLOCKS
    # ========================================================

    cleaned_blocks = clean_blocks(
        doc.blocks
    )

    if not cleaned_blocks:
        raise ValueError(
            f"No usable blocks after cleaning "
            f"{doc.file_name}"
        )

    logger.info(
        f"Cleaning complete: "
        f"{len(doc.blocks)} → "
        f"{len(cleaned_blocks)} blocks"
    )

    # ========================================================
    # 2. BUILD CANDIDATE UNITS
    # ========================================================

    units = build_candidate_units(
        cleaned_blocks
    )

    if not units:
        raise ValueError(
            f"No candidate units created "
            f"for {doc.file_name}"
        )

    logger.info(
        f"Created {len(units)} "
        f"candidate units"
    )

    # ========================================================
    # 3. HANDLE SINGLE-UNIT DOCUMENT
    # ========================================================

    if len(units) == 1:

        assembled = [
            _finalize_units(
                [units[0]]
            )
        ]

    else:

        # ====================================================
        # 4. EMBED CANDIDATE UNITS
        # ====================================================

        embeddings = embed_units(
            units
        )

        # ====================================================
        # 5. COMPARE ADJACENT UNITS
        # ====================================================

        similarities = (
            calculate_similarities(
                embeddings
            )
        )

        # ====================================================
        # 6. FIND DYNAMIC BOUNDARY THRESHOLD
        # ====================================================

        threshold = (
            find_dynamic_threshold(
                similarities
            )
        )

        logger.info(
            f"Semantic boundary threshold: "
            f"{threshold:.4f}"
        )

        # ====================================================
        # 7. ASSEMBLE FINAL CHUNKS
        # ====================================================

        assembled = _assemble_chunks(
            units=units,
            similarities=similarities,
            threshold=threshold,
        )

    # ========================================================
    # 8. CREATE FINAL CHUNK OBJECTS
    # ========================================================

    total_chunks = len(assembled)

    final_chunks: list[Chunk] = []

    for index, item in enumerate(
        assembled
    ):

        chunk_id = (
            f"{doc.file_name}"
            f"__chunk_{index}"
        )

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
                    "section_path": (
                        item["section_path"]
                    ),
                    "page_numbers": (
                        item["page_numbers"]
                    ),
                    "block_types": (
                        item["block_types"]
                    ),
                    "source_block_ids": (
                        item["block_ids"]
                    ),
                },
            )
        )

    logger.info(
        f"Produced {total_chunks} "
        f"final chunks from "
        f"{doc.file_name}"
    )

    return final_chunks


def _assemble_chunks(
    units: list[CandidateUnit],
    similarities: list[float],
    threshold: float,
) -> list[dict]:
    """
    Walk through candidate units in document order
    and decide whether to merge or split.

    Structure alone does not split.
    Semantic similarity alone does not split.

    A split happens when:

    1. The chunk exceeds the size limit

    OR

    2. There is both:
       - a semantic topic change
       - a structural section change
    """

    chunks: list[dict] = []

    current_units = [
        units[0]
    ]

    for index in range(
        1,
        len(units),
    ):

        previous_unit = (
            units[index - 1]
        )

        current_unit = (
            units[index]
        )

        similarity = (
            similarities[index - 1]
        )

        # Text currently inside
        # the chunk being built.
        current_text = (
            _combine_unit_text(
                current_units
            )
        )

        # What the chunk would look like
        # if we added the next unit.
        proposed_text = (
            current_text
            + "\n\n"
            + current_unit.text
        )

        # --------------------------------------------
        # SIGNAL 1: SIZE
        # --------------------------------------------

        exceeds_max_size = (
            len(proposed_text)
            > settings.chunk_size
        )

        # --------------------------------------------
        # SIGNAL 2: SEMANTIC CHANGE
        # --------------------------------------------

        semantic_break = (
            similarity < threshold
        )

        # --------------------------------------------
        # SIGNAL 3: STRUCTURAL CHANGE
        # --------------------------------------------

        strong_structure_break = (
            _is_strong_structure_break(
                previous=previous_unit,
                current=current_unit,
            )
        )

        # --------------------------------------------
        # FINAL DECISION
        # --------------------------------------------

        should_split = (
            exceeds_max_size
            or (
                semantic_break
                and strong_structure_break
            )
        )

        logger.debug(
            f"Boundary {index - 1} → {index}: "
            f"similarity={similarity:.4f}, "
            f"semantic_break={semantic_break}, "
            f"structure_break="
            f"{strong_structure_break}, "
            f"size_break={exceeds_max_size}, "
            f"split={should_split}"
        )

        if should_split:
            last_unit_is_heading = (
                    current_units[-1].block_types
                    and current_units[-1].block_types[-1] == "heading"
            )

            if last_unit_is_heading:
                # Don't cut right after a heading — pull in the next
                # unit first so the heading isn't left with no content.
                current_units.append(current_unit)
            else:
                chunks.append(_finalize_units(current_units))
                current_units = [current_unit]
        else:
            current_units.append(current_unit)

    # The loop never automatically saves
    # the final group, so save it here.
    if current_units:

        chunks.append(
            _finalize_units(
                current_units
            )
        )

    return chunks


def _is_strong_structure_break(
    previous: CandidateUnit,
    current: CandidateUnit,
) -> bool:
    """
    Check whether two adjacent units belong
    to different document sections.

    Structure is only supporting evidence.
    It does not create a split by itself.
    """

    if (
        previous.section_path
        and current.section_path
        and previous.section_path
        != current.section_path
    ):
        return True

    return False


def _combine_unit_text(
    units: list[CandidateUnit],
) -> str:
    """
    Combine the text of multiple candidate units.
    """

    return "\n\n".join(
        unit.text
        for unit in units
    )


def _finalize_units(
    units: list[CandidateUnit],
) -> dict:
    """
    Convert a group of candidate units into
    one final chunk representation.
    """

    # ========================================================
    # FIND SECTION CONTEXT
    # ========================================================

    section_path: list[str] = []

    for unit in units:

        if unit.section_path:

            section_path = (
                unit.section_path.copy()
            )

            break

    # ========================================================
    # COMBINE CONTENT
    # ========================================================

    content = _combine_unit_text(
        units
    )

    # ========================================================
    # ADD SECTION CONTEXT
    # ========================================================

    if section_path:

        context = " > ".join(
            section_path
        )

        text = (
            f"Section context: {context}"
            f"\n\n"
            f"{content}"
        )

    else:

        text = content

    # ========================================================
    # COLLECT PAGE NUMBERS
    # ========================================================

    page_numbers = sorted({
        page
        for unit in units
        for page in unit.page_numbers
    })

    # ========================================================
    # COLLECT BLOCK TYPES
    # ========================================================

    block_types = list(
        dict.fromkeys(
            block_type
            for unit in units
            for block_type
            in unit.block_types
        )
    )

    # ========================================================
    # COLLECT ORIGINAL BLOCK IDs
    # ========================================================

    block_ids = [
        block_id
        for unit in units
        for block_id
        in unit.block_ids
    ]

    return {
        "text": text,
        "section_path": section_path,
        "page_numbers": page_numbers,
        "block_types": block_types,
        "block_ids": block_ids,
    }