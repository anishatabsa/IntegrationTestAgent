"""
Feedback collector — auto-generates FeedbackItems from failing test results.
These feed the pattern learner and future RAG context.
"""
from __future__ import annotations

import re
from uuid import UUID

from aita.domain.enums import FeedbackSource, FeedbackType
from aita.domain.models import FeedbackItem, TestCase, TestResult


_STATUS_CODE_RE = re.compile(r"Expected status code (\d+) but got (\d+)")
_ASSERTION_RE = re.compile(r"AssertionError|assert .* ==")
_COMPILE_RE = re.compile(r"SyntaxError|CompilationError|cannot find symbol")


def _classify(error: str) -> tuple[FeedbackType, str | None]:
    if _COMPILE_RE.search(error):
        return FeedbackType.COMPILATION_ERROR, None
    m = _STATUS_CODE_RE.search(error)
    if m:
        expected, actual = m.group(1), m.group(2)
        return (
            FeedbackType.WRONG_STATUS_CODE,
            f"Expected {expected}, got {actual}. Adjust assertion or check auth requirement.",
        )
    if _ASSERTION_RE.search(error):
        return FeedbackType.ASSERTION_FAILURE, None
    return FeedbackType.RUNTIME_ERROR, None


class FeedbackCollector:
    async def from_results(
        self,
        run_id: UUID,
        results: list[TestResult],
        tests: dict[str, TestCase],
    ) -> list[FeedbackItem]:
        items: list[FeedbackItem] = []

        for result in results:
            if result.status in ("passed", "skipped"):
                continue
            error = result.error_message or result.stderr or ""
            if not error:
                continue

            fb_type, fix_hint = _classify(error)
            items.append(FeedbackItem(
                run_id=run_id,
                endpoint_id=result.test_case_id,
                source=FeedbackSource.AUTO,
                feedback_type=fb_type,
                description=error[:500],
                fix_hint=fix_hint,
            ))

        return items

    async def from_yaml(self, yaml_path: str) -> list[FeedbackItem]:
        """Import QE-provided feedback from a YAML file."""
        import yaml
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        items: list[FeedbackItem] = []
        for entry in (data or []):
            items.append(FeedbackItem(
                source=FeedbackSource.QE,
                feedback_type=FeedbackType(entry.get("type", "custom")),
                description=entry.get("description", ""),
                fix_hint=entry.get("fix_hint"),
                metadata=entry.get("metadata", {}),
            ))
        return items
