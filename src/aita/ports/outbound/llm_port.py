"""Outbound port — LLM interaction."""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMPort(ABC):

    @abstractmethod
    async def complete(self, prompt: str, system: str | None = None, max_tokens: int = 8192) -> str:
        """Send a prompt, return the completion text."""

    @abstractmethod
    async def complete_cached(self, prompt: str, system: str | None = None) -> tuple[str, bool]:
        """
        Send a prompt with Redis-backed caching.
        Returns (response_text, was_cache_hit).
        """

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Estimate token count for the given text."""
