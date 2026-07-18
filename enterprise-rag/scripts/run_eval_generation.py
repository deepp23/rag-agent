# scripts/run_eval_generation.py
from qdrant_client import QdrantClient

from src.core.config import get_settings
from src.ingestion.models import Chunk
from src.evaluation.dataset_generator import generate_evaluation_dataset

settings = get_settings()


def load_chunks_from_qdrant(collection_name: str) -> list[Chunk]:
    client = QdrantClient(
        url=settings.qdrant_url,
    )

    chunks: list[Chunk] = []
    next_offset = None

    while True:
        points, next_offset = client.scroll(
            collection_name=collection_name,
            limit=256,
            offset=next_offset,
            with_payload=True,
            with_vectors=False,
        )

        for point in points:
            payload = point.payload

            chunks.append(
                Chunk(
                    chunk_id=payload.get("chunk_id", str(point.id)),
                    file_name=payload.get("file_name", ""),
                    file_type=payload.get("file_type", ""),
                    text=payload.get("text", ""),
                    chunk_index=payload.get("chunk_index", 0),
                    total_chunks=payload.get("total_chunks", 0),
                    metadata=payload.get("metadata", {}),
                )
            )

        if next_offset is None:
            break

    return chunks


def main():
    chunks = load_chunks_from_qdrant(collection_name="enterprise_rag")
    print(f"Loaded {len(chunks)} chunks from Qdrant")

    dataset = generate_evaluation_dataset(
        chunks=chunks,
        dataset_name="baseline_eval_v2",
        output_path="data/eval/baseline_eval_v2.json",
        questions_per_chunk=5,
        max_chunks=10,
    )
    print(f"Generated {len(dataset.test_cases)} test cases")


if __name__ == "__main__":
    main()