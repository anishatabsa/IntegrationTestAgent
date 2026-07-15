"""Base class for healer rules."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from aita.domain.enums import Language


@dataclass
class RuleResult:
    content: str
    modified: bool = False
    dropped: bool = False
    error: str = ""
    tokens_used: int = 0


class BaseHealerRule(ABC):
    @property
    @abstractmethod
    def stage_name(self) -> str:
        ...

    @abstractmethod
    async def apply(self, content: str, language: Language) -> RuleResult:
        ...
