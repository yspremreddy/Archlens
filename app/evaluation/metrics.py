"""Standard IR evaluation metrics, generic and independent of ArchLens's
retrieval implementation — used by tests/test_evaluation.py against both
the synthetic dataset and the real public corpus (data/samples/public/).

All metrics use binary relevance (a document either is or isn't in the
golden relevant set for a query) since that's what the golden sets
(app/evaluation/golden.py) define — a graded-relevance nDCG would need
graded ground truth this project doesn't have and would be fabricated
(engineering guideline 3), so binary-relevance nDCG is used instead.
"""

import math


def recall_at_k(ranked_doc_ids: list[str], relevant_doc_ids: set[str], k: int) -> float:
    """Fraction of relevant_doc_ids found within the top k of ranked_doc_ids."""
    if not relevant_doc_ids:
        return 0.0
    top_k = set(ranked_doc_ids[:k])
    return len(top_k & relevant_doc_ids) / len(relevant_doc_ids)


def reciprocal_rank(ranked_doc_ids: list[str], relevant_doc_ids: set[str]) -> float:
    """1/rank of the first relevant doc in ranked_doc_ids, else 0."""
    for i, doc_id in enumerate(ranked_doc_ids, start=1):
        if doc_id in relevant_doc_ids:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked_doc_ids: list[str], relevant_doc_ids: set[str], k: int) -> float:
    """Binary-relevance nDCG@k."""
    if not relevant_doc_ids:
        return 0.0
    dcg = sum(
        1.0 / math.log2(i + 1)
        for i, doc_id in enumerate(ranked_doc_ids[:k], start=1)
        if doc_id in relevant_doc_ids
    )
    ideal_hits = min(len(relevant_doc_ids), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
