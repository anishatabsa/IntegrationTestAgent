"""
Stage 2 — Rule-based repair: fix known patterns without calling LLM.
- self.api_client fixture issues in Python
- Hardcoded localhost URLs
- Wrong import paths
- Wrong status code assertions (401 on unauthenticated endpoint)
"""
from __future__ import annotations

import re

from aita.core.healer.rules.base_rule import BaseHealerRule, RuleResult
from aita.domain.enums import Language


class RuleBasedRepairRule(BaseHealerRule):
    @property
    def stage_name(self) -> str:
        return "rule_based_repair"

    async def apply(self, content: str, language: Language) -> RuleResult:
        if language == Language.PYTHON:
            fixed, changed = self._fix_python(content)
        elif language == Language.JAVA:
            fixed, changed = self._fix_java(content)
        else:
            return RuleResult(content=content)

        return RuleResult(content=fixed, modified=changed)

    # ── Python fixes ─────────────────────────────────────────────────────────

    def _fix_python(self, content: str) -> tuple[str, bool]:
        original = content
        content = self._fix_self_api_client(content)
        content = self._fix_hardcoded_urls(content)
        content = self._fix_base_url_env(content)
        return content, content != original

    def _fix_self_api_client(self, content: str) -> str:
        """Ensure self.api_client = requests.Session() in setUp or __init__."""
        if "self.api_client" not in content:
            return content
        if "self.api_client = " in content:
            return content

        # Insert setup method after class definition line
        lines = content.splitlines()
        result = []
        class_indent = ""
        inserted = False
        for i, line in enumerate(lines):
            result.append(line)
            if re.match(r"^class \w+", line) and not inserted:
                class_indent = "    "
                result.append(f"{class_indent}def setUp(self):")
                result.append(f"{class_indent}    import requests, os")
                result.append(f"{class_indent}    self.base_url = os.environ.get('BASE_URL', 'http://localhost:8080')")
                result.append(f"{class_indent}    self.api_client = requests.Session()")
                inserted = True
        return "\n".join(result)

    def _fix_hardcoded_urls(self, content: str) -> str:
        """Replace hardcoded localhost URLs with {self.base_url}."""
        return re.sub(
            r'["\']http://localhost:\d+([^"\']*)["\']',
            lambda m: f'f"{{self.base_url}}{m.group(1)}"',
            content,
        )

    def _fix_base_url_env(self, content: str) -> str:
        """Ensure BASE_URL is read from environment."""
        if "BASE_URL" in content or "base_url" in content.lower():
            return content
        # Prepend environment read after imports
        lines = content.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                insert_at = i + 1
        lines.insert(insert_at, "BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8080')")
        return "\n".join(lines)

    # ── Java fixes ───────────────────────────────────────────────────────────

    def _fix_java(self, content: str) -> tuple[str, bool]:
        original = content
        content = self._fix_java_base_uri(content)
        return content, content != original

    def _fix_java_base_uri(self, content: str) -> str:
        """Replace hardcoded URLs in RestAssured.baseURI with System.getProperty."""
        return re.sub(
            r'RestAssured\.baseURI\s*=\s*"http://localhost:\d+"',
            'RestAssured.baseURI = System.getProperty("BASE_URL", "http://localhost:8080")',
            content,
        )
