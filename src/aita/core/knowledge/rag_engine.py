"""
Three-tier RAG engine.
Fuses results from Naive RAG + Agentic RAG (+ optional Graph RAG)
using Reciprocal Rank Fusion (RRF).
"""
from __future__ import annotations

import structlog

from aita.core.knowledge.fusion_ranker import rrf_fuse
from aita.domain.models import FeedbackItem, LearnedPattern, RAGContext

logger = structlog.get_logger()


class RAGEngine:
    def __init__(
        self,
        naive_rag,      # NaiveRAG
        agentic_rag,    # AgenticRAG
        graph_rag=None, # GraphRAG (optional)
        pattern_store=None,   # async callable: (service_name) -> list[LearnedPattern]
        feedback_store=None,  # async callable: (service_name) -> list[FeedbackItem]
    ) -> None:
        self._naive = naive_rag
        self._agentic = agentic_rag
        self._graph = graph_rag
        self._patterns = pattern_store
        self._feedback = feedback_store

    async def enrich(self, service_name: str, query: str) -> RAGContext:
        """Run all tiers in parallel and fuse results."""
        import asyncio

        tasks = [
            self._naive.search(service_name, query),
            self._agentic.search(service_name, query),
        ]
        if self._graph:
            tasks.append(self._graph.search(service_name, query))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        ranked_lists: list[list[str]] = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning("rag_tier_failed", error=str(r))
            elif r:
                ranked_lists.append(r)

        fused = rrf_fuse(ranked_lists)

        # Fetch learned patterns and past feedback
        patterns: list[LearnedPattern] = []
        feedback: list[FeedbackItem] = []

        if self._patterns:
            try:
                patterns = await self._patterns(service_name)
            except Exception as exc:
                logger.warning("pattern_fetch_failed", error=str(exc))

        if self._feedback:
            try:
                feedback = await self._feedback(service_name)
            except Exception as exc:
                logger.warning("feedback_fetch_failed", error=str(exc))

        return RAGContext(
            patterns=patterns[:10],
            feedback_items=feedback[:10],
            knowledge_snippets=fused[:10],
        )
