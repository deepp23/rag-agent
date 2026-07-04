import re
from collections import defaultdict

from src.ingestion.models import DocumentBlock


def normalize_text(
    text: str,
) -> str:

    text = text.lower()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def clean_blocks(
    blocks: list[DocumentBlock],
) -> list[DocumentBlock]:

    blocks = [
        block
        for block in blocks
        if block.text.strip()
    ]

    blocks = _remove_repeated_page_noise(
        blocks
    )

    return blocks


def _remove_repeated_page_noise(
    blocks: list[DocumentBlock],
) -> list[DocumentBlock]:

    pages_by_text: dict[
        str,
        set[int],
    ] = defaultdict(set)

    total_pages = {
        block.page_number
        for block in blocks
        if block.page_number is not None
    }

    # Don't perform repetition detection
    # on very small documents.

    if len(total_pages) < 3:
        return blocks

    for block in blocks:

        if block.page_number is None:
            continue

        normalized = normalize_text(
            block.text
        )

        # Headers and footers are usually short.
        # Do not classify large content as page noise.

        if len(normalized) > 150:
            continue

        pages_by_text[normalized].add(
            block.page_number
        )

    repeated_text = set()

    minimum_page_count = max(
        3,
        int(len(total_pages) * 0.5),
    )

    for text, pages in pages_by_text.items():

        if len(pages) >= minimum_page_count:
            repeated_text.add(text)

    cleaned = []

    for block in blocks:

        normalized = normalize_text(
            block.text
        )

        if normalized in repeated_text:
            continue

        # Remove standalone page numbers

        if re.fullmatch(
            r"(page\s*)?\d+",
            normalized,
        ):
            continue

        cleaned.append(block)

    return cleaned