"""
Stage 3 — Cross-language contamination detection (CRITICAL).

Detects:
- Python `def test_X(self):` inside Java class → drop affected methods
- Java `void testX()` / `@Test` annotations inside Python file → remove them
- Any mixing of language-specific syntax in the wrong file
"""
from __future__ import annotations

import re

from aita.core.healer.rules.base_rule import BaseHealerRule, RuleResult
from aita.domain.enums import Language

# Python patterns that should NOT appear in Java
_PYTHON_IN_JAVA = [
    re.compile(r"^\s+def test\w*\s*\(self", re.MULTILINE),
    re.compile(r"^\s+import requests\b", re.MULTILINE),
    re.compile(r"^\s+self\.\w+\s*=", re.MULTILINE),
    re.compile(r"^\s+assert\s+\w+\s*==", re.MULTILINE),  # pytest-style assert
]

# Java patterns that should NOT appear in Python
_JAVA_IN_PYTHON = [
    re.compile(r"^\s+@Test\b", re.MULTILINE),
    re.compile(r"\bpublic\s+void\s+test\w+\s*\(", re.MULTILINE),
    re.compile(r"\bimport\s+org\.junit\b", re.MULTILINE),
    re.compile(r"\bimport\s+io\.restassured\b", re.MULTILINE),
]

_JAVA_METHOD_BLOCK_RE = re.compile(
    r"([ \t]+def\s+test\w*\s*\(self[^)]*\)\s*:[^\n]*(?:\n(?:[ \t]+[^\n]*)|\n)+)",
    re.MULTILINE,
)


class CrossLangContaminationRule(BaseHealerRule):
    @property
    def stage_name(self) -> str:
        return "cross_lang_contamination"

    async def apply(self, content: str, language: Language) -> RuleResult:
        if language == Language.JAVA:
            return self._check_java(content)
        elif language == Language.PYTHON:
            return self._check_python(content)
        return RuleResult(content=content)

    def _check_java(self, content: str) -> RuleResult:
        """Remove Python method blocks from Java code."""
        contaminated = any(pat.search(content) for pat in _PYTHON_IN_JAVA)
        if not contaminated:
            return RuleResult(content=content)

        # Remove Python def blocks line by line
        lines = content.splitlines()
        cleaned: list[str] = []
        skip = False
        skip_indent = 0

        for line in lines:
            # Start of a Python def inside Java
            if re.match(r"^(\s+)def test\w*\s*\(self", line):
                skip = True
                skip_indent = len(line) - len(line.lstrip())
                cleaned.append("    // HEALER: removed Python-contaminated method block")
                continue

            if skip:
                stripped = line.strip()
                indent = len(line) - len(line.lstrip()) if line.strip() else skip_indent + 1
                if stripped and indent <= skip_indent:
                    skip = False
                    cleaned.append(line)
                # else: still inside contaminated block, skip it
            else:
                # Remove standalone Python imports
                if re.match(r"\s+import requests\b", line):
                    continue
                cleaned.append(line)

        return RuleResult(content="\n".join(cleaned), modified=True)

    def _check_python(self, content: str) -> RuleResult:
        """Remove Java annotations and method signatures from Python code."""
        contaminated = any(pat.search(content) for pat in _JAVA_IN_PYTHON)
        if not contaminated:
            return RuleResult(content=content)

        lines = content.splitlines()
        cleaned = [
            line for line in lines
            if not any(pat.match(line) for pat in [
                re.compile(r"\s*@Test\b"),
                re.compile(r"\s*public\s+void\s+test"),
                re.compile(r"\s*import\s+org\.junit"),
                re.compile(r"\s*import\s+io\.restassured"),
            ])
        ]
        return RuleResult(content="\n".join(cleaned), modified=True)
