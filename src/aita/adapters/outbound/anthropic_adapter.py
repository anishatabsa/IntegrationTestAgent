"""Anthropic Claude adapter implementing LLMPort."""
from __future__ import annotations

import hashlib
import json

import structlog
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from aita.domain.exceptions import LLMError
from aita.ports.outbound.cache_port import CachePort
from aita.ports.outbound.llm_port import LLMPort

logger = structlog.get_logger()

_LLM_CACHE_PREFIX = "llm:"


class AnthropicAdapter(LLMPort):
    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int,
        temperature: float,
        cache: CachePort,
        cache_ttl: int = 86400,
    ) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._cache = cache
        self._cache_ttl = cache_ttl

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def complete(self, prompt: str, system: str | None = None, max_tokens: int = 0) -> str:
        kwargs = {
            "model": self._model,
            "max_tokens": max_tokens or self._max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        try:
            response = await self._client.messages.create(**kwargs)
            return response.content[0].text
        except Exception as exc:
            logger.error("anthropic_api_error", error=str(exc), model=self._model, exc_info=True)
            raise LLMError(f"Anthropic API error: {exc}") from exc

    async def complete_cached(self, prompt: str, system: str | None = None) -> tuple[str, bool]:
        cache_key = _LLM_CACHE_PREFIX + hashlib.sha256(
            (prompt + (system or "")).encode()
        ).hexdigest()

        cached = await self._cache.get(cache_key)
        if cached:
            return cached, True

        response = await self.complete(prompt, system=system)
        await self._cache.set(cache_key, response, ttl=self._cache_ttl)
        return response, False

    def count_tokens(self, text: str) -> int:
        # Approximate: Claude tokenises at ~3.5 chars/token
        return max(1, len(text) // 4)
