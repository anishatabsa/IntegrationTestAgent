"""Reciprocal Rank Fusion (RRF) for combining results from multiple RAG tiers."""
from __future__ import annotations

from collections import defaultdict

K = 60  # RRF constant


def rrf_fuse(ranked_lists: list[list[str]], k: int = K) -> list[str]:
    """
    Given multiple ranked lists of text snippets, return a single
    fused and re-ranked list using RRF scoring.
    """
    scores: dict[str, float] = defaultdict(float)

    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            scores[item] += 1.0 / (k + rank)

    return sorted(scores, key=lambda x: scores[x], reverse=True)
