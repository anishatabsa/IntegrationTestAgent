"""Ollama local LLM adapter implementing LLMPort."""
from __future__ import annotations

import hashlib

import structlog
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from aita.domain.exceptions import LLMError
from aita.ports.outbound.cache_port import CachePort
from aita.ports.outbound.llm_port import LLMPort

logger = structlog.get_logger()

_LLM_CACHE_PREFIX = "llm:"


class OllamaAdapter(LLMPort):
    def __init__(
        self,
        base_url: str,
        model: str,
        cache: CachePort,
        cache_ttl: int = 86400,
        max_tokens: int = 8192,
        temperature: float = 0.2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._cache = cache
        self._cache_ttl = cache_ttl
        self._max_tokens = max_tokens
        self._temperature = temperature

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def complete(self, prompt: str, system: str | None = None, max_tokens: int = 0) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens or self._max_tokens,
                "temperature": self._temperature,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["message"]["content"]
        except Exception as exc:
            raise LLMError(f"Ollama API error: {exc}") from exc

    async def complete_cached(self, prompt: str, system: str | None = None) -> tuple[str, bool]:
        key = _LLM_CACHE_PREFIX + hashlib.sha256(
            (prompt + (system or "")).encode()
        ).hexdigest()
        cached = await self._cache.get(key)
        if cached:
            return cached, True
        response = await self.complete(prompt, system=system)
        await self._cache.set(key, response, ttl=self._cache_ttl)
        return response, False

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
