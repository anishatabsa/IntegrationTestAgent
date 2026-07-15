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
