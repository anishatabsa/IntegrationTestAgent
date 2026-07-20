"""
In-memory pattern store — persists learned patterns and feedback across pipeline runs
within the same server process. Passed to RAGEngine as pattern_store / feedback_store
callables so that run N+1 benefits from run N failures without requiring a database.
"""
from __future__ import annotations

import structlog

from aita.domain.models import FeedbackItem, LearnedPattern

logger = structlog.get_logger()

_MAX_FEEDBACK_PER_SERVICE = 50


class InMemoryPatternStore:
    """Thread-safe (GIL-protected) in-memory store for learned patterns and feedback."""

    def __init__(self) -> None:
        # service_name -> list[LearnedPattern]
        self._patterns: dict[str, list[LearnedPattern]] = {}
        # service_name -> list[FeedbackItem]
        self._feedback: dict[str, list[FeedbackItem]] = {}

    def save(
        self,
        service_name: str,
        patterns: list[LearnedPattern],
        feedback: list[FeedbackItem],
    ) -> None:
        """Merge new patterns into the store (upsert by pattern_key, sum occurrences)."""
        existing = {p.pattern_key: p for p in self._patterns.get(service_name, [])}
        for pat in patterns:
            key = pat.pattern_key
            if key in existing:
                existing[key].occurrence_count += pat.occurrence_count
            else:
                existing[key] = pat
        self._patterns[service_name] = sorted(
            existing.values(), key=lambda p: p.occurrence_count, reverse=True
        )

        # Keep a rolling window of the most recent feedback items
        current = self._feedback.get(service_name, [])
        combined = current + feedback
        self._feedback[service_name] = combined[-_MAX_FEEDBACK_PER_SERVICE:]

        logger.info(
            "pattern_store_updated",
            service=service_name,
            total_patterns=len(self._patterns[service_name]),
            total_feedback=len(self._feedback[service_name]),
        )

    async def get_patterns(self, service_name: str) -> list[LearnedPattern]:
        return self._patterns.get(service_name, [])

    async def get_feedback(self, service_name: str) -> list[FeedbackItem]:
        return self._feedback.get(service_name, [])
