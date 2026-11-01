"""Deterministic ranking metrics for RAG retrieval evaluation.

Relevance labels must be human-reviewed. This module intentionally returns
None for metrics that cannot be computed from a case's available labels.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence


def _unique(values: Iterable[str]) -> list[str]:
    """Normalize IDs to strings and preserve first occurrence."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def precision_at_k(retrieved_ids: Sequence[str], relevant_ids: Iterable[str], k: int) -> float | None:
    """Fraction of the first k retrieved items that are relevant.

    Uses k as the denominator, including when fewer than k items were
    returned. This makes results comparable across queries with short lists.
    Returns None when no relevance labels exist.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    relevant = set(_unique(relevant_ids))
    if not relevant:
        return None
    retrieved = _unique(retrieved_ids)[:k]
    return sum(item in relevant for item in retrieved) / k


def recall_at_k(retrieved_ids: Sequence[str], relevant_ids: Iterable[str], k: int) -> float | None:
    """Fraction of known relevant items found in the first k results."""
    if k < 1:
        raise ValueError("k must be >= 1")
    relevant = set(_unique(relevant_ids))
    if not relevant:
        return None
    retrieved = set(_unique(retrieved_ids)[:k])
    return len(retrieved & relevant) / len(relevant)


def reciprocal_rank(retrieved_ids: Sequence[str], relevant_ids: Iterable[str]) -> float | None:
    """Reciprocal rank of the first relevant result (MRR contribution)."""
    relevant = set(_unique(relevant_ids))
    if not relevant:
        return None
    for rank, item in enumerate(_unique(retrieved_ids), start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(
    retrieved_ids: Sequence[str],
    relevance_grades: Mapping[str, int | float],
    k: int,
) -> float | None:
    """Normalized discounted cumulative gain using graded relevance.

    DCG gain is (2**grade - 1), discounted by log2(rank + 1). A zero-valued
    or empty grade map is not a usable relevance judgement and returns None.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    grades = {str(key): float(value) for key, value in relevance_grades.items() if key and float(value) > 0}
    if not grades:
        return None

    import math

    ranked = _unique(retrieved_ids)[:k]
    dcg = sum(
        (2 ** grades.get(item, 0.0) - 1) / math.log2(rank + 1)
        for rank, item in enumerate(ranked, start=1)
    )
    ideal_grades = sorted(grades.values(), reverse=True)[:k]
    idcg = sum(
        (2 ** grade - 1) / math.log2(rank + 1)
        for rank, grade in enumerate(ideal_grades, start=1)
    )
    return dcg / idcg if idcg else None


def evaluate_retrieval_case(
    retrieved_ids: Sequence[str],
    relevant_ids: Iterable[str] | None = None,
    relevance_grades: Mapping[str, int | float] | None = None,
    ks: Sequence[int] = (3, 5, 8),
) -> dict[str, float | int | None]:
    """Return per-query retrieval metrics and label coverage metadata."""
    relevant = _unique(relevant_ids or [])
    grades = relevance_grades or {}
    result: dict[str, float | int | None] = {
        "relevance_label_count": len(relevant) if relevant else len(grades),
        "retrieved_unique_count": len(_unique(retrieved_ids)),
        "mrr": reciprocal_rank(retrieved_ids, relevant) if relevant else None,
    }
    for k in ks:
        result[f"precision_at_{k}"] = precision_at_k(retrieved_ids, relevant, k) if relevant else None
        result[f"recall_at_{k}"] = recall_at_k(retrieved_ids, relevant, k) if relevant else None
        result[f"ndcg_at_{k}"] = ndcg_at_k(retrieved_ids, grades, k) if grades else None
    return result


def aggregate_metric_rows(rows: Sequence[Mapping[str, float | int | None]]) -> dict[str, float | int | None]:
    """Macro-average available numeric metric values and report coverage."""
    if not rows:
        return {"scored_cases": 0, "total_cases": 0}
    metric_names = sorted({key for row in rows for key in row if key != "relevance_label_count" and key != "retrieved_unique_count"})
    summary: dict[str, float | int | None] = {
        "total_cases": len(rows),
        "scored_cases": sum(bool(row.get("relevance_label_count")) for row in rows),
    }
    for name in metric_names:
        values = [row[name] for row in rows if isinstance(row.get(name), (int, float))]
        summary[f"mean_{name}"] = sum(values) / len(values) if values else None
        summary[f"{name}_coverage"] = len(values) / len(rows)
    return summary
