"""Stage 1 — Static analysis: AST parse Python, javac compile Java."""
from __future__ import annotations

import ast
import re
import subprocess
import tempfile
from pathlib import Path

from aita.core.healer.rules.base_rule import BaseHealerRule, RuleResult
from aita.domain.enums import Language


class StaticAnalysisRule(BaseHealerRule):
    @property
    def stage_name(self) -> str:
        return "static_analysis"

    async def apply(self, content: str, language: Language) -> RuleResult:
        if language == Language.PYTHON:
            return self._check_python(content)
        elif language == Language.JAVA:
            return self._check_java(content)
        # Other languages: pass through
        return RuleResult(content=content)

    def _check_python(self, content: str) -> RuleResult:
        try:
            ast.parse(content)
            return RuleResult(content=content)
        except SyntaxError as exc:
            # Attempt simple fixes: truncated def line
            fixed = self._fix_truncated_def(content)
            try:
                ast.parse(fixed)
                return RuleResult(content=fixed, modified=True)
            except SyntaxError:
                return RuleResult(
                    content=content,
                    dropped=True,
                    error=f"Python SyntaxError: {exc}",
                )

    def _fix_truncated_def(self, content: str) -> str:
        """Fix lines like `def test_` missing `(self):` closure."""
        lines = content.splitlines()
        fixed = []
        for line in lines:
            stripped = line.rstrip()
            # Truncated def: ends with `def test` or `def test_<name>` without `(`
            if re.match(r"^\s+def test\w*$", stripped):
                indent = len(line) - len(line.lstrip())
                fixed.append(" " * indent + "# HEALER: removed truncated method")
                continue
            fixed.append(line)
        return "\n".join(fixed)

    def _check_java(self, content: str) -> RuleResult:
        """Use javac to detect compilation errors (requires JDK on PATH)."""
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Extract class name for file naming
                match = re.search(r"public\s+class\s+(\w+)", content)
                class_name = match.group(1) if match else "TestClass"
                java_file = Path(tmpdir) / f"{class_name}.java"
                java_file.write_text(content, encoding="utf-8")

                result = subprocess.run(
                    ["javac", str(java_file)],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    return RuleResult(content=content)

                # Check for cross-language contamination first (handled in stage 3)
                if "reached end of file" in result.stderr:
                    fixed = self._fix_unclosed_braces(content)
                    return RuleResult(content=fixed, modified=True)

                return RuleResult(
                    content=content,
                    dropped=False,  # Let LLM repair attempt in stage 5
                    error=result.stderr[:500],
                )
        except FileNotFoundError:
            # javac not available — skip Java static analysis
            return RuleResult(content=content)
        except subprocess.TimeoutExpired:
            return RuleResult(content=content, error="javac timeout")

    def _fix_unclosed_braces(self, content: str) -> str:
        """Add missing closing braces at end of file."""
        opens = content.count("{")
        closes = content.count("}")
        missing = opens - closes
        if missing > 0:
            return content.rstrip() + "\n" + ("}\n" * missing)
        return content
