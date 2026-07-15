"""Redis adapter implementing CachePort."""
from __future__ import annotations

import json
from typing import Any

import structlog
from redis.asyncio import Redis

from aita.domain.exceptions import CacheError
from aita.ports.outbound.cache_port import CachePort

logger = structlog.get_logger()


class RedisAdapter(CachePort):
    def __init__(self, redis: Redis) -> None:
        self._r = redis

    async def get(self, key: str) -> Any | None:
        try:
            val = await self._r.get(key)
            return json.loads(val) if val else None
        except Exception as exc:
            raise CacheError(f"Redis GET failed: {exc}") from exc

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        try:
            serialised = json.dumps(value)
            if ttl:
                await self._r.setex(key, ttl, serialised)
            else:
                await self._r.set(key, serialised)
        except Exception as exc:
            raise CacheError(f"Redis SET failed: {exc}") from exc

    async def delete(self, key: str) -> None:
        await self._r.delete(key)

    async def exists(self, key: str) -> bool:
        return bool(await self._r.exists(key))

    async def acquire_lock(self, key: str, ttl: int = 60) -> bool:
        lock_key = f"lock:{key}"
        result = await self._r.set(lock_key, "1", nx=True, ex=ttl)
        return result is True

    async def release_lock(self, key: str) -> None:
        await self._r.delete(f"lock:{key}")

    async def publish(self, channel: str, message: dict) -> None:
        await self._r.publish(channel, json.dumps(message))
