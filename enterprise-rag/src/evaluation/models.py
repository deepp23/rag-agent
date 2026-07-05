from dataclasses import dataclass, field


@dataclass
class EvaluationCase:
    question: str
    expected_answer: str

    relevant_chunk_ids: list[str]

    category: str

    answerable: bool = True

    source_file: str = ""

    metadata: dict = field(
        default_factory=dict
    )


@dataclass
class EvaluationDataset:
    dataset_name: str
    test_cases: list[EvaluationCase]