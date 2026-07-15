"""FastAPI / Python source scanner — detects @router.get / @app.post decorators."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from aita.core.scanner.source_scanner import BaseSourceScanner
from aita.domain.enums import Language
from aita.domain.models import ScannedComponent

_DECORATOR_RE = re.compile(
    r"@(?:app|router|APIRouter\(\))\.(get|post|put|delete|patch|head|options)"
    r'\s*\(\s*["\']([^"\']*)["\']'
)
_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


class FastAPIScanner(BaseSourceScanner):
    @property
    def language(self) -> Language:
        return Language.PYTHON

    async def scan(self, repo_dir: Path) -> list[ScannedComponent]:
        components: list[ScannedComponent] = []

        for py_file in repo_dir.rglob("*.py"):
            # Skip test files
            if py_file.name.startswith("test_") or "tests" in py_file.parts:
                continue

            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if not any(kw in content for kw in ("@app.", "@router.", "APIRouter")):
                continue

            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue

                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call):
                        continue
                    func = decorator.func
                    if not isinstance(func, ast.Attribute):
                        continue
                    method = func.attr.lower()
                    if method not in _HTTP_METHODS:
                        continue

                    # Extract path from first argument
                    path = ""
                    if decorator.args:
                        first = decorator.args[0]
                        if isinstance(first, ast.Constant):
                            path = str(first.value)

                    # Look for security dependencies (Depends(get_current_user) etc.)
                    auth_anns: list[str] = []
                    for kw in decorator.keywords:
                        if kw.arg == "dependencies":
                            auth_anns.append(ast.unparse(kw.value))

                    op_id = node.name
                    components.append(ScannedComponent(
                        operation_id=op_id,
                        controller_class=py_file.stem,
                        method_name=node.name,
                        http_method=method.upper(),
                        url_pattern=path,
                        auth_annotations=auth_anns,
                        validation_annotations=[],
                    ))

        return components
