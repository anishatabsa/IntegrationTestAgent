"""Outbound port — cache (Redis)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CachePort(ABC):

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Return deserialized value or None."""

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store serialized value, optionally with TTL in seconds."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a key."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists."""

    @abstractmethod
    async def acquire_lock(self, key: str, ttl: int = 60) -> bool:
        """Acquire a distributed lock. Returns True if acquired."""

    @abstractmethod
    async def release_lock(self, key: str) -> None:
        """Release a distributed lock."""

    @abstractmethod
    async def publish(self, channel: str, message: dict) -> None:
        """Publish an event to a pub/sub channel (SSE streaming)."""
