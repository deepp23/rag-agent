import json
import random
from dataclasses import asdict
from pathlib import Path

from google import genai
from google.genai import types

from src.core.config import get_settings
from src.core.logger import get_logger

from src.ingestion.models import Chunk

from src.evaluation.models import (
    EvaluationCase,
    EvaluationDataset,
)


logger = get_logger(__name__)
settings = get_settings()


client_genai = genai.Client(
    api_key=settings.gemini_api_key
)


# ============================================================
# CONFIGURATION
# ============================================================


DEFAULT_QUESTIONS_PER_CHUNK = 2


ALLOWED_CATEGORIES = {
    "simple_fact",
    "paraphrased",
    "numerical",
    "conditional",
    "boundary_condition",
}


# ============================================================
# MAIN FUNCTION
# ============================================================


def generate_evaluation_dataset(
    chunks: list[Chunk],
    dataset_name: str,
    output_path: str | Path,
    questions_per_chunk: int = (
        DEFAULT_QUESTIONS_PER_CHUNK
    ),
    max_chunks: int | None = None,
    random_seed: int = 42,
) -> EvaluationDataset:
    """
    Generate an evaluation dataset automatically
    from final RAG chunks.

    Flow:

    Final chunks
        ↓
    Select useful chunks
        ↓
    Send each chunk to Gemini
        ↓
    Generate question + expected answer
        ↓
    Attach source chunk ID automatically
        ↓
    Validate
        ↓
    Deduplicate
        ↓
    Save JSON
    """

    logger.info(
        f"Starting evaluation dataset generation "
        f"from {len(chunks)} chunks."
    )

    # --------------------------------------------------------
    # 1. FILTER BAD CHUNKS
    # --------------------------------------------------------

    usable_chunks = [
        chunk
        for chunk in chunks
        if _is_usable_chunk(chunk)
    ]

    logger.info(
        f"{len(usable_chunks)} of "
        f"{len(chunks)} chunks are usable "
        f"for evaluation generation."
    )

    if not usable_chunks:
        raise ValueError(
            "No usable chunks available "
            "for dataset generation."
        )

    # --------------------------------------------------------
    # 2. OPTIONALLY SAMPLE CHUNKS
    # --------------------------------------------------------

    if (
        max_chunks is not None
        and len(usable_chunks) > max_chunks
    ):

        random_generator = random.Random(
            random_seed
        )

        usable_chunks = (
            random_generator.sample(
                usable_chunks,
                max_chunks,
            )
        )

        logger.info(
            f"Sampled {len(usable_chunks)} chunks."
        )

    # --------------------------------------------------------
    # 3. GENERATE TEST CASES
    # --------------------------------------------------------

    all_cases: list[EvaluationCase] = []

    for index, chunk in enumerate(
        usable_chunks,
        start=1,
    ):

        logger.info(
            f"Generating questions for "
            f"chunk {index}/{len(usable_chunks)}: "
            f"{chunk.chunk_id}"
        )

        try:

            generated_cases = (
                _generate_cases_from_chunk(
                    chunk=chunk,
                    questions_per_chunk=(
                        questions_per_chunk
                    ),
                )
            )

            all_cases.extend(
                generated_cases
            )

            logger.info(
                f"Generated "
                f"{len(generated_cases)} "
                f"cases from {chunk.chunk_id}"
            )

        except Exception as error:

            logger.error(
                f"Failed to generate cases "
                f"from {chunk.chunk_id}: "
                f"{error}",
                exc_info=True,
            )

            # Do not stop the complete generation
            # because one chunk failed.
            continue

    # --------------------------------------------------------
    # 4. DEDUPLICATE
    # --------------------------------------------------------

    unique_cases = _deduplicate_cases(
        all_cases
    )

    logger.info(
        f"Deduplication: "
        f"{len(all_cases)} → "
        f"{len(unique_cases)} cases"
    )

    # --------------------------------------------------------
    # 5. CREATE DATASET
    # --------------------------------------------------------

    dataset = EvaluationDataset(
        dataset_name=dataset_name,
        test_cases=unique_cases,
    )

    # --------------------------------------------------------
    # 6. SAVE DATASET
    # --------------------------------------------------------

    save_evaluation_dataset(
        dataset=dataset,
        output_path=output_path,
    )

    logger.info(
        f"Evaluation dataset created: "
        f"{len(unique_cases)} test cases"
    )

    return dataset


# ============================================================
# GENERATE FROM ONE CHUNK
# ============================================================


def _generate_cases_from_chunk(
    chunk: Chunk,
    questions_per_chunk: int,
) -> list[EvaluationCase]:
    """
    Ask Gemini to generate evaluation questions
    whose answers are fully supported by one chunk.
    """

    prompt = f"""
You are creating a high-quality evaluation dataset for an enterprise RAG system.

Generate exactly {questions_per_chunk} test questions from the source text below.

STRICT REQUIREMENTS:

1. Every question must be answerable completely from the source text.

2. The expected answer must contain only information explicitly stated in the source text.

3. Do not use outside knowledge.

4. Do not mention:
   - chunks
   - chunk IDs
   - source text
   - context
   - documents
   - sections
   - retrieval

5. Write questions the way a real employee would naturally ask an enterprise assistant.

6. Do not copy sentences from the source text as questions.

7. Prefer questions that test understanding rather than simple keyword matching.

8. Vary the question types when possible.

Allowed categories:

- simple_fact
  A direct factual question.

- paraphrased
  The question uses different wording from the source.

- numerical
  The answer depends on an exact number, amount, duration, limit, or deadline.

- conditional
  The answer depends on a condition or requirement.

- boundary_condition
  The question tests exact wording such as under, over, at least, more than, or exactly.

9. The expected answer should be concise but complete.

10. Do not generate a question if the answer requires information outside this source text.

Return only valid JSON in this exact format:

{{
    "test_cases": [
        {{
            "question": "question here",
            "expected_answer": "answer here",
            "category": "one allowed category"
        }}
    ]
}}

SOURCE TEXT:

{chunk.text}
"""

    response = client_genai.models.generate_content(
        model=settings.generation_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type=(
                "application/json"
            ),
        ),
    )

    if not response.text:
        raise ValueError(
            "Gemini returned an empty response."
        )

    data = json.loads(
        response.text
    )

    raw_cases = data.get(
        "test_cases",
        []
    )

    evaluation_cases: list[
        EvaluationCase
    ] = []

    for raw_case in raw_cases:

        question = (
            raw_case
            .get("question", "")
            .strip()
        )

        expected_answer = (
            raw_case
            .get("expected_answer", "")
            .strip()
        )

        category = (
            raw_case
            .get("category", "")
            .strip()
        )

        # --------------------------------------------
        # BASIC VALIDATION
        # --------------------------------------------

        if not question:
            continue

        if not expected_answer:
            continue

        if category not in ALLOWED_CATEGORIES:
            category = "paraphrased"

        # --------------------------------------------
        # CREATE EVALUATION CASE
        # --------------------------------------------

        evaluation_cases.append(
            EvaluationCase(
                question=question,
                expected_answer=(
                    expected_answer
                ),
                relevant_chunk_ids=[
                    chunk.chunk_id
                ],
                category=category,
                answerable=True,
                source_file=chunk.file_name,
                metadata={
                    "generation_type": (
                        "single_chunk"
                    ),
                    "source_chunk_index": (
                        chunk.chunk_index
                    ),
                },
            )
        )

    return evaluation_cases


# ============================================================
# CHUNK FILTERING
# ============================================================


def _is_usable_chunk(
    chunk: Chunk,
) -> bool:
    """
    Avoid generating test questions from chunks
    that are too short or contain very little
    useful information.
    """

    text = chunk.text.strip()

    if not text:
        return False

    # Very short chunks usually create
    # poor evaluation questions.
    if len(text) < 150:
        return False

    word_count = len(
        text.split()
    )

    if word_count < 25:
        return False

    return True


# ============================================================
# DEDUPLICATION
# ============================================================


def _deduplicate_cases(
    cases: list[EvaluationCase],
) -> list[EvaluationCase]:
    """
    Remove exact and near-basic duplicate questions.

    For the first version, normalize the question
    and remove exact normalized duplicates.
    """

    seen_questions: set[str] = set()

    unique_cases: list[
        EvaluationCase
    ] = []

    for case in cases:

        normalized = (
            case.question
            .lower()
            .strip()
            .rstrip("?")
        )

        normalized = " ".join(
            normalized.split()
        )

        if normalized in seen_questions:
            continue

        seen_questions.add(
            normalized
        )

        unique_cases.append(
            case
        )

    return unique_cases


# ============================================================
# SAVE DATASET
# ============================================================


def save_evaluation_dataset(
    dataset: EvaluationDataset,
    output_path: str | Path,
) -> None:

    path = Path(
        output_path
    )

    # Create parent folder automatically.
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = asdict(
        dataset
    )

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    logger.info(
        f"Dataset saved to: {path}"
    )