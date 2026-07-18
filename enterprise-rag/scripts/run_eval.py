import json
import math
import secrets
import time
import uuid

import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from src.agent.graph import run_rag
from src.auth.security import hash_password
from src.db.models import User, Workspace
from src.db.session import SessionLocal


model = SentenceTransformer("all-MiniLM-L6-v2")

TOP_K = 5
EVAL_USER_EMAIL = "eval@enterprise-rag.local"


def get_or_create_eval_workspace() -> str:
    """
    run_rag now requires a workspace_id to scope retrieval to (retrieval is
    per-tenant). The eval corpus must already have been ingested into this
    same workspace via POST /api/v1/ingest (using this eval user's token)
    before running this script — this only resolves the workspace id, it
    does not ingest anything.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == EVAL_USER_EMAIL).first()
        if user is None:
            user = User(email=EVAL_USER_EMAIL, hashed_password=hash_password(secrets.token_urlsafe(32)))
            db.add(user)
            db.flush()
            db.add(Workspace(owner_id=user.id))
            db.commit()
            db.refresh(user)
            print(f"Created eval user/workspace ({EVAL_USER_EMAIL}) — ingest the eval corpus into it first.")

        workspace = db.query(Workspace).filter(Workspace.owner_id == user.id).first()
        return str(workspace.id)
    finally:
        db.close()


def precision_at_k(retrieved, relevant, k):
    retrieved = retrieved[:k]
    return len(set(retrieved) & relevant) / k


def recall_at_k(retrieved, relevant, k):
    retrieved = retrieved[:k]
    return len(set(retrieved) & relevant) / len(relevant)


def reciprocal_rank(retrieved, relevant):
    for i, chunk in enumerate(retrieved):
        if chunk in relevant:
            return 1 / (i + 1)
    return 0


def dcg(retrieved, relevant):
    score = 0
    for i, chunk in enumerate(retrieved):
        if chunk in relevant:
            score += 1 / math.log2(i + 2)
    return score


def ndcg(retrieved, relevant):
    ideal = dcg(list(relevant), relevant)
    if ideal == 0:
        return 0
    return dcg(retrieved, relevant) / ideal


def semantic_similarity(answer, reference):
    emb = model.encode([answer, reference])
    return cosine_similarity([emb[0]], [emb[1]])[0][0]


def main():

    with open("data/eval/baseline_eval_v1.json", encoding="utf-8") as f:
        dataset = json.load(f)

    workspace_id = get_or_create_eval_workspace()

    rows = []
    hit_count = 0
    total_latency = 0

    for sample in dataset["test_cases"]:

        start = time.perf_counter()

        result = run_rag(
            query=sample["question"],
            workspace_id=workspace_id,
            conversation_id=str(uuid.uuid4()),
            history=[],
        )

        latency = time.perf_counter() - start
        total_latency += latency

        retrieved_full = [
            c["metadata"]["chunk_id"]
            for c in result["retrieved_chunks"]
        ]
        retrieved = retrieved_full[:TOP_K]   # <- enforce the cutoff once, use everywhere below

        relevant = set(sample["relevant_chunk_ids"])

        hit = int(len(set(retrieved) & relevant) > 0)
        hit_count += hit

        similarity = semantic_similarity(
            result["response"],
            sample["expected_answer"],
        )

        rows.append(
            {
                "question": sample["question"],
                "hit": hit,
                "precision@5": precision_at_k(retrieved, relevant, TOP_K),
                "recall@5": recall_at_k(retrieved, relevant, TOP_K),
                "MRR": reciprocal_rank(retrieved, relevant),
                "nDCG@5": ndcg(retrieved, relevant),
                "semantic_similarity": similarity,
                "latency_seconds": latency,
            }
        )

    df = pd.DataFrame(rows)

    print("=" * 60)
    print("Retrieval Hit Rate:", hit_count / len(df))
    print("Precision@5:", df["precision@5"].mean())
    print("Recall@5:", df["recall@5"].mean())
    print("MRR:", df["MRR"].mean())
    print("nDCG@5:", df["nDCG@5"].mean())
    print("Semantic Similarity:", df["semantic_similarity"].mean())
    print("Average Latency:", total_latency / len(df))
    print("=" * 60)

    df.to_csv("data/eval/evaluation_results.csv", index=False)


if __name__ == "__main__":
    main()