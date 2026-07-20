"""Spec parser registry and base class (Strategy pattern)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from aita.domain.enums import SpecFormat
from aita.domain.exceptions import SpecNotFoundError
from aita.domain.models import EndpointSpec

_SPEC_CANDIDATES = [
    ("openapi.yaml", SpecFormat.OPENAPI_3),
    ("openapi.yml", SpecFormat.OPENAPI_3),
    ("swagger.yaml", SpecFormat.SWAGGER_2),
    ("swagger.yml", SpecFormat.SWAGGER_2),
    ("openapi.json", SpecFormat.OPENAPI_3),
    ("swagger.json", SpecFormat.SWAGGER_2),
]


class BaseSpecParser(ABC):
    @property
    @abstractmethod
    def spec_format(self) -> SpecFormat:
        ...

    @abstractmethod
    async def parse(self, repo_dir: Path) -> list[EndpointSpec]:
        ...

    def _find_spec_file(self, repo_dir: Path) -> Path:
        """Search common locations in the repo for the spec file."""
        # Priority 1: well-known fixed locations
        search_dirs = [
            repo_dir,
            repo_dir / "src" / "main" / "resources",
            repo_dir / "docs",
            repo_dir / "api",
            repo_dir / "spec",
            repo_dir / "openapi",
        ]
        for candidate, _ in _SPEC_CANDIDATES:
            for search_dir in search_dirs:
                p = search_dir / candidate
                if p.exists():
                    return p

        # Priority 2: recursive glob (up to 4 levels deep) — slower but catches any layout
        for candidate, _ in _SPEC_CANDIDATES:
            matches = sorted(repo_dir.rglob(candidate))
            # Skip hidden dirs and common non-spec dirs
            for m in matches:
                if any(part.startswith(".") for part in m.parts):
                    continue
                if any(part in {"node_modules", "__pycache__", ".venv", "target"} for part in m.parts):
                    continue
                return m

        raise SpecNotFoundError(f"No spec file found in {repo_dir}")


class SpecParserRegistry:
    """Detects the spec format and returns the appropriate parser."""

    def __init__(self, parsers: list[BaseSpecParser]) -> None:
        self._parsers: dict[SpecFormat, BaseSpecParser] = {p.spec_format: p for p in parsers}

    def detect(self, repo_dir: Path) -> BaseSpecParser:
        # Reuse BaseSpecParser._find_spec_file logic via any registered parser
        for candidate, fmt in _SPEC_CANDIDATES:
            # Priority 1: fixed locations
            for search_dir in [
                repo_dir,
                repo_dir / "src" / "main" / "resources",
                repo_dir / "docs",
                repo_dir / "api",
                repo_dir / "spec",
                repo_dir / "openapi",
            ]:
                if (search_dir / candidate).exists():
                    parser = self._parsers.get(fmt)
                    if parser:
                        return parser

            # Priority 2: recursive glob
            for m in sorted(repo_dir.rglob(candidate)):
                if any(p.startswith(".") for p in m.parts):
                    continue
                if any(p in {"node_modules", "__pycache__", ".venv", "target"} for p in m.parts):
                    continue
                parser = self._parsers.get(fmt)
                if parser:
                    return parser

        raise SpecNotFoundError(f"No parseable spec found in {repo_dir}")
