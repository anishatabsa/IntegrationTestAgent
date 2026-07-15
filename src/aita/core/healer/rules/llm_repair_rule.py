"""
Stage 5 — LLM repair.
Called only when prior stages left issues (SEMANTIC_ISSUE comments, compilation errors).
Max 2 LLM attempts, then drop the test.
"""
from __future__ import annotations

import re

import structlog

from aita.core.healer.rules.base_rule import BaseHealerRule, RuleResult
from aita.domain.enums import Language
from aita.ports.outbound.llm_port import LLMPort

logger = structlog.get_logger()

MAX_ATTEMPTS = 2

_ISSUE_RE = re.compile(r"# SEMANTIC_ISSUE: (.+)")
_JAVA_ERR_RE = re.compile(r"// (HEALER|SEMANTIC_ISSUE): (.+)")

_SYSTEM = """\
You are a test repair specialist. You will receive broken or incomplete test code with
inline comments marking the issues. Fix ONLY the marked issues and return the corrected
code with no explanation, no markdown fences. Preserve all existing passing logic.
"""


def _has_issues(content: str, language: Language) -> bool:
    if language == Language.PYTHON:
        return bool(_ISSUE_RE.search(content))
    return bool(_JAVA_ERR_RE.search(content))


class LLMRepairRule(BaseHealerRule):
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    @property
    def stage_name(self) -> str:
        return "llm_repair"

    async def apply(self, content: str, language: Language) -> RuleResult:
        if not _has_issues(content, language):
            return RuleResult(content=content)

        tokens_used = 0
        current = content

        for attempt in range(1, MAX_ATTEMPTS + 1):
            prompt = (
                f"The following {language.value} test code has marked issues.\n"
                f"Fix all lines starting with '# SEMANTIC_ISSUE:' or '// HEALER:'.\n\n"
                f"{current}"
            )
            tokens_used += self._llm.count_tokens(prompt)

            try:
                repaired = await self._llm.complete(prompt, system=_SYSTEM)
            except Exception as exc:
                logger.warning("llm_repair_failed", attempt=attempt, error=str(exc))
                continue

            tokens_used += self._llm.count_tokens(repaired)

            if not _has_issues(repaired, language):
                logger.info("llm_repair_success", attempt=attempt)
                return RuleResult(content=repaired, modified=True, tokens_used=tokens_used)

            current = repaired
            logger.debug("llm_repair_still_has_issues", attempt=attempt)

        # All attempts exhausted
        return RuleResult(
            content=current,
            dropped=True,
            error=f"LLM repair exhausted {MAX_ATTEMPTS} attempts without resolving all issues",
            tokens_used=tokens_used,
        )
