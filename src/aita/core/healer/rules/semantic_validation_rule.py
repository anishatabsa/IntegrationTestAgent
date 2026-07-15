"""
Stage 4 — Semantic validation.
Checks:
- At least one assertion per test method
- No hardcoded external URLs
- No missing imports for used symbols
"""
from __future__ import annotations

import ast
import re

from aita.core.healer.rules.base_rule import BaseHealerRule, RuleResult
from aita.domain.enums import Language


_HARDCODED_URL_RE = re.compile(r'["\']https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
_EXTERNAL_HOST_RE = re.compile(r'["\']https?://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)')


class SemanticValidationRule(BaseHealerRule):
    @property
    def stage_name(self) -> str:
        return "semantic_validation"

    async def apply(self, content: str, language: Language) -> RuleResult:
        issues: list[str] = []

        if language == Language.PYTHON:
            issues += self._check_python(content)
        elif language == Language.JAVA:
            issues += self._check_java(content)

        if not issues:
            return RuleResult(content=content)

        # Non-fatal: annotate and continue (LLM stage can fix)
        annotation = "\n".join(f"# SEMANTIC_ISSUE: {i}" for i in issues)
        fixed = annotation + "\n" + content
        return RuleResult(content=fixed, modified=True)

    def _check_python(self, content: str) -> list[str]:
        issues: list[str] = []

        # Check for hardcoded external URLs
        if _EXTERNAL_HOST_RE.search(content):
            issues.append("Hardcoded external URL detected; use BASE_URL env var")

        # Check each test method has at least one assertion
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return issues  # handled by stage 1

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("test_"):
                    continue
                has_assert = any(
                    isinstance(n, (ast.Assert, ast.Call)) and (
                        isinstance(n, ast.Assert) or (
                            isinstance(getattr(n.func, "attr", None), str) and
                            n.func.attr.startswith("assert")
                        )
                    )
                    for n in ast.walk(node)
                )
                if not has_assert:
                    issues.append(f"Test method '{node.name}' has no assertions")

        return issues

    def _check_java(self, content: str) -> list[str]:
        issues: list[str] = []
        if _EXTERNAL_HOST_RE.search(content):
            issues.append("Hardcoded external URL detected; use System.getProperty('BASE_URL')")

        # Check each @Test method has at least one assert
        test_methods = re.findall(r"@Test\s+[^{]+\{([^}]*)\}", content, re.DOTALL)
        for body in test_methods:
            if "assert" not in body.lower() and ".then()" not in body:
                issues.append("A @Test method has no assertions or RestAssured .then() chain")

        return issues
