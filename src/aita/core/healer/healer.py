"""
5-Stage Healer Pipeline (Chain of Responsibility pattern).

Stage 1: Static analysis (AST / javac)
Stage 2: Rule-based repair
Stage 3: Cross-language contamination detection  ← CRITICAL
Stage 4: Semantic validation
Stage 5: LLM repair (max 2 attempts, then drop)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from aita.core.healer.rules.base_rule import BaseHealerRule
from aita.domain.models import TestCase

logger = structlog.get_logger()

MAX_LLM_ATTEMPTS = 2


@dataclass
class HealResult:
    content: str
    was_modified: bool = False
    dropped: bool = False
    error: str = ""
    tokens_used: int = 0
    stages_applied: list[str] = field(default_factory=list)


class HealerPipeline:
    """
    Runs each rule stage in order. If a stage cannot fix the issue after
    exhausting its strategies, it marks the result as dropped.
    """

    def __init__(self, rules: list[BaseHealerRule]) -> None:
        self._rules = rules

    async def heal(self, test_case: TestCase) -> HealResult:
        content = test_case.content
        original = content
        total_tokens = 0
        stages: list[str] = []

        for rule in self._rules:
            result = await rule.apply(content, test_case.language)
            total_tokens += result.tokens_used

            if result.dropped:
                return HealResult(
                    content=content,
                    dropped=True,
                    error=result.error,
                    tokens_used=total_tokens,
                    stages_applied=stages + [rule.stage_name],
                )

            if result.modified:
                content = result.content
                stages.append(rule.stage_name)
                logger.debug("healer_stage_applied", stage=rule.stage_name)

        return HealResult(
            content=content,
            was_modified=content != original,
            tokens_used=total_tokens,
            stages_applied=stages,
        )
