"""FastAPI / Python source scanner — detects @router.get / @app.post decorators."""
from __future__ import annotations

import ast
import base64
import re
from pathlib import Path

import structlog

from aita.core.scanner.source_scanner import BaseSourceScanner
from aita.domain.enums import Language
from aita.domain.models import ScannedComponent

logger = structlog.get_logger()

_DECORATOR_RE = re.compile(
    r"@(?:app|router|APIRouter\(\))\.(get|post|put|delete|patch|head|options)"
    r'\s*\(\s*["\']([^"\']*)["\']'
)
_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}

_FASTAPI_KEYWORDS = ("@app.", "@router.", "APIRouter")


def _parse_github_repo(url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from a GitHub HTTPS URL."""
    url = url.rstrip("/").removesuffix(".git")
    if "github.com/" not in url:
        return None
    after = url.split("github.com/", 1)[1]
    parts = after.split("/")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None


def _extract_components(content: str, stem: str) -> list[ScannedComponent]:
    """Parse FastAPI route decorators from source *content* and return components."""
    if not any(kw in content for kw in _FASTAPI_KEYWORDS):
        return []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    components: list[ScannedComponent] = []
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

            path = ""
            if decorator.args:
                first = decorator.args[0]
                if isinstance(first, ast.Constant):
                    path = str(first.value)

            auth_anns: list[str] = []
            for kw in decorator.keywords:
                if kw.arg == "dependencies":
                    auth_anns.append(ast.unparse(kw.value))

            components.append(ScannedComponent(
                operation_id=node.name,
                controller_class=stem,
                method_name=node.name,
                http_method=method.upper(),
                url_pattern=path,
                auth_annotations=auth_anns,
                validation_annotations=[],
            ))

    return components


class FastAPIScanner(BaseSourceScanner):
    @property
    def language(self) -> Language:
        return Language.PYTHON

    async def scan(self, repo_dir: Path) -> list[ScannedComponent]:
        """Scan a local repository directory for FastAPI route decorators."""
        components: list[ScannedComponent] = []

        for py_file in repo_dir.rglob("*.py"):
            # Skip test files
            if py_file.name.startswith("test_") or "tests" in py_file.parts:
                continue

            content = py_file.read_text(encoding="utf-8", errors="ignore")
            components.extend(_extract_components(content, py_file.stem))

        return components

    async def scan_from_github(
        self, repo_url: str, token: str, branch: str = "main"
    ) -> list[ScannedComponent]:
        """Scan a GitHub repository for FastAPI routes without cloning locally.

        Delegates all synchronous PyGithub I/O to a thread-pool executor so the
        asyncio event loop is never blocked (PyGithub uses the synchronous
        ``requests`` library under the hood).
        """
        import asyncio
        return await asyncio.to_thread(self._scan_github_sync, repo_url, token, branch)

    def _scan_github_sync(
        self, repo_url: str, token: str, branch: str
    ) -> list[ScannedComponent]:
        """Synchronous body of scan_from_github — runs in a thread pool."""
        from github import Github, GithubException  # PyGithub

        parsed = _parse_github_repo(repo_url)
        if not parsed:
            logger.warning("fastapi_scanner_github_bad_url", repo_url=repo_url)
            return []

        owner, repo_name = parsed
        gh = Github(token)
        try:
            repo = gh.get_repo(f"{owner}/{repo_name}")
        except GithubException as exc:
            logger.warning("fastapi_scanner_github_repo_error", error=str(exc))
            return []

        # Resolve the target branch (fall back to repo default)
        try:
            target_sha = repo.get_branch(branch).commit.sha
        except GithubException:
            try:
                target_sha = repo.get_branch(repo.default_branch).commit.sha
                logger.info(
                    "fastapi_scanner_branch_fallback",
                    requested=branch,
                    used=repo.default_branch,
                )
            except GithubException as exc:
                logger.warning("fastapi_scanner_github_branch_error", error=str(exc))
                return []

        # Walk the full tree in one API call (recursive=True) instead of
        # one call per directory.
        try:
            tree = repo.get_git_tree(target_sha, recursive=True)
        except GithubException as exc:
            logger.warning("fastapi_scanner_github_tree_error", error=str(exc))
            return []

        components: list[ScannedComponent] = []
        for item in tree.tree:
            if item.type != "blob" or not item.path.endswith(".py"):
                continue

            # Skip test files and virtual-env directories
            path_parts = item.path.replace("\\", "/").split("/")
            filename = path_parts[-1]
            if filename.startswith("test_") or any(
                p in path_parts for p in ("tests", ".venv", "venv", "site-packages", "__pycache__")
            ):
                continue

            # Fetch content via the blob SHA we already have from the tree —
            # avoids a second path-resolution round-trip compared to get_contents().
            try:
                blob = repo.get_git_blob(item.sha)
                encoding = blob.encoding or "base64"
                if encoding == "base64":
                    raw = base64.b64decode(blob.content).decode("utf-8", errors="ignore")
                else:
                    raw = blob.content
            except (GithubException, Exception) as exc:
                logger.debug("fastapi_scanner_blob_error", path=item.path, error=str(exc))
                continue

            stem = filename.removesuffix(".py")
            components.extend(_extract_components(raw, stem))

        logger.info(
            "fastapi_scanner_github_done",
            repo=f"{owner}/{repo_name}",
            component_count=len(components),
        )
        return components
