"""Source scanner registry and base class (Strategy pattern)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from aita.domain.enums import Language
from aita.domain.models import ScannedComponent


class BaseSourceScanner(ABC):
    @property
    @abstractmethod
    def language(self) -> Language:
        ...

    @abstractmethod
    async def scan(self, repo_dir: Path) -> list[ScannedComponent]:
        ...

    async def scan_from_github(
        self, repo_url: str, token: str, branch: str = "main"
    ) -> list[ScannedComponent]:
        """Scan source files fetched directly from GitHub (no local clone).

        Subclasses that support GitHub API scanning should override this method.
        The default implementation logs a warning and returns an empty list.
        """
        import structlog as _log
        _log.get_logger().warning(
            "scan_from_github_not_supported",
            scanner=type(self).__name__,
            repo_url=repo_url,
        )
        return []


class SourceScannerRegistry:
    def __init__(self, scanners: list[BaseSourceScanner]) -> None:
        self._scanners: dict[Language, BaseSourceScanner] = {s.language: s for s in scanners}

    def get(self, language: Language | str | None) -> BaseSourceScanner | None:
        if language is None:
            return None
        try:
            return self._scanners.get(Language(language))
        except ValueError:
            return None
