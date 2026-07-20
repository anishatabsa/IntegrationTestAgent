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
        # Strip markdown fences the LLM sometimes wraps output in despite instructions.
        # ```python ... ``` on line 1 causes SyntaxError, which drops the whole file.
        stripped = self._strip_markdown_fences(content)
        if stripped != content:
            content = stripped

        try:
            tree = ast.parse(content)
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

        # Collect all module-level lines that will raise NameError at import/collection time.
        # (1) References to 'self' outside any class/function
        # (2) Bare name expressions (e.g. LLM garbage like 'feEND') — valid syntax but NameError
        bad_lines: list[int] = []
        bad_lines.extend(self._find_module_level_self(tree))
        bad_lines.extend(self._find_module_level_bare_names(tree))

        if bad_lines:
            fixed = self._remove_module_level_self_lines(content, bad_lines)
            try:
                ast.parse(fixed)
                return RuleResult(content=fixed, modified=True)
            except SyntaxError:
                return RuleResult(
                    content=content,
                    dropped=True,
                    error=f"Module-level issues on lines {bad_lines} could not be auto-fixed",
                )

        return RuleResult(content=content)

    def _strip_markdown_fences(self, content: str) -> str:
        """Remove ```python ... ``` or ``` ... ``` fences the LLM wraps code in.

        The system prompt says "Output ONLY valid Python code, no markdown fences"
        but some model versions still wrap output. A leading fence produces a
        SyntaxError on line 1, causing the whole file to be dropped.
        """
        stripped = content.strip()
        # Opening fence: ```python or ``` optionally followed by whitespace/newline
        if re.match(r'^```(?:python)?\s*\n', stripped):
            stripped = re.sub(r'^```(?:python)?\s*\n', '', stripped)
            # Remove the matching closing fence at the very end
            stripped = re.sub(r'\n```\s*$', '', stripped)
            return stripped
        return content

    def _find_module_level_bare_names(self, tree: ast.Module) -> list[int]:
        """Return line numbers of module-level bare name expressions (e.g. 'feEND').

        These are syntactically valid but raise NameError at collection time.
        Pattern: top-level ast.Expr whose value is a plain ast.Name (not a call,
        not a constant, not an assignment) — always LLM output garbage.
        """
        bad: list[int] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Name):
                bad.append(node.lineno)
        return bad

    def _find_module_level_self(self, tree: ast.Module) -> list[int]:
        """Return line numbers of statements at module level that reference 'self'."""
        bad: list[int] = []
        for node in ast.iter_child_nodes(tree):
            # Only look at top-level statements (not inside class/function)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and child.id == "self":
                    bad.append(getattr(child, "lineno", 0))
        return bad

    def _remove_module_level_self_lines(self, content: str, bad_lines: set | list) -> str:
        """Drop or neutralise lines that reference 'self' at module level."""
        bad_set = set(bad_lines)
        out = []
        for i, line in enumerate(content.splitlines(), start=1):
            if i in bad_set:
                out.append(f"# HEALER: removed module-level self reference: {line.strip()}")
            else:
                out.append(line)
        return "\n".join(out)

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
