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
        search_dirs = [repo_dir, repo_dir / "src" / "main" / "resources", repo_dir / "docs"]
        for candidate, _ in _SPEC_CANDIDATES:
            for search_dir in search_dirs:
                p = search_dir / candidate
                if p.exists():
                    return p
        raise SpecNotFoundError(f"No spec file found in {repo_dir}")


class SpecParserRegistry:
    """Detects the spec format and returns the appropriate parser."""

    def __init__(self, parsers: list[BaseSpecParser]) -> None:
        self._parsers: dict[SpecFormat, BaseSpecParser] = {p.spec_format: p for p in parsers}

    def detect(self, repo_dir: Path) -> BaseSpecParser:
        for candidate, fmt in _SPEC_CANDIDATES:
            for search_dir in [
                repo_dir,
                repo_dir / "src" / "main" / "resources",
                repo_dir / "docs",
            ]:
                if (search_dir / candidate).exists():
                    parser = self._parsers.get(fmt)
                    if parser:
                        return parser
        raise SpecNotFoundError(f"No parseable spec found in {repo_dir}")
