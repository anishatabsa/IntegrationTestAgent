"""Outbound port — vector store (Qdrant)."""
from __future__ import annotations

from abc import ABC, abstractmethod


class VectorStorePort(ABC):

    @abstractmethod
    async def upsert(self, collection: str, texts: list[str], metadata: list[dict]) -> list[str]:
        """Embed and upsert texts. Returns list of point IDs."""

    @abstractmethod
    async def search(self, collection: str, query: str, top_k: int = 5) -> list[dict]:
        """Semantic search. Returns list of {text, score, metadata} dicts."""

    @abstractmethod
    async def delete(self, collection: str, ids: list[str]) -> None:
        """Delete points by ID."""

    @abstractmethod
    async def delete_by_filter(self, collection: str, filter_key: str, filter_value: str) -> None:
        """Delete all points whose *filter_key* payload field equals *filter_value*."""

    @abstractmethod
    async def ensure_collection(self, collection: str, vector_size: int) -> None:
        """Create collection if it doesn't exist."""
