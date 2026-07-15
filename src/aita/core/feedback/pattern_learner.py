"""
Pattern learner — distils recurring feedback into LearnedPatterns
that are persisted to PostgreSQL and surfaced via RAG.
"""
from __future__ import annotations

from collections import Counter

import structlog

from aita.domain.enums import FeedbackType
from aita.domain.models import FeedbackItem, LearnedPattern

logger = structlog.get_logger()

_PROMPT_HINTS: dict[FeedbackType, str] = {
    FeedbackType.WRONG_STATUS_CODE: (
        "Double-check the expected HTTP status codes. "
        "If auth is optional, test both authenticated and unauthenticated paths."
    ),
    FeedbackType.ASSERTION_FAILURE: (
        "Assert on response fields by name, not position. "
        "Use response.json() and check specific keys."
    ),
    FeedbackType.COMPILATION_ERROR: (
        "Ensure all imports are present. "
        "Python: do not mix Java syntax. Java: close all braces."
    ),
    FeedbackType.CROSS_LANG_CONTAMINATION: (
        "Generate ONLY the target language. Never mix Python `def test_` inside Java."
    ),
    FeedbackType.HARDCODED_VALUE: (
        "Use dynamic test data. Never hardcode IDs, names, or prices."
    ),
}


class PatternLearner:
    """In-memory pattern learner; the persist step writes patterns to Postgres."""

    async def learn(
        self, service_name: str, feedback_items: list[FeedbackItem]
    ) -> list[LearnedPattern]:
        if not feedback_items:
            return []

        counts = Counter(fb.feedback_type for fb in feedback_items)
        patterns: list[LearnedPattern] = []

        for fb_type, count in counts.most_common():
            hint = _PROMPT_HINTS.get(fb_type, "")
            pattern = LearnedPattern(
                pattern_type=str(fb_type),
                description=f"{count} occurrence(s) of {fb_type} in service '{service_name}'",
                service_id=None,  # resolved by persist layer
                pattern_key=f"{service_name}:{fb_type}",
                prompt_snippet=hint,
                occurrence_count=count,
            )
            patterns.append(pattern)
            logger.info("pattern_learned", service=service_name, type=fb_type, count=count)

        return patterns
