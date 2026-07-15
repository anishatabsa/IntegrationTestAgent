"""Qdrant vector store adapter implementing VectorStorePort."""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
)

from aita.ports.outbound.vector_store_port import VectorStorePort

logger = structlog.get_logger()

_DEFAULT_VECTOR_SIZE = 1536  # text-embedding-3-small / nomic-embed-text


class QdrantAdapter(VectorStorePort):
    def __init__(self, client: AsyncQdrantClient, embedder) -> None:
        self._client = client
        self._embedder = embedder  # callable: list[str] -> list[list[float]]

    async def upsert(
        self, collection: str, texts: list[str], metadata: list[dict]
    ) -> list[str]:
        vectors = await self._embedder(texts)
        ids = [str(uuid.uuid4()) for _ in texts]
        points = [
            PointStruct(id=pid, vector=vec, payload={**meta, "text": text})
            for pid, vec, text, meta in zip(ids, vectors, texts, metadata)
        ]
        await self._client.upsert(collection_name=collection, points=points)
        return ids

    async def search(
        self, collection: str, query: str, top_k: int = 5
    ) -> list[dict]:
        vector = (await self._embedder([query]))[0]
        results = await self._client.search(
            collection_name=collection,
            query_vector=vector,
            limit=top_k,
            with_payload=True,
        )
        return [
            {"text": r.payload.get("text", ""), "score": r.score, "metadata": r.payload}
            for r in results
        ]

    async def delete(self, collection: str, ids: list[str]) -> None:
        from qdrant_client.models import PointIdsList
        await self._client.delete(
            collection_name=collection,
            points_selector=PointIdsList(points=ids),
        )

    async def ensure_collection(self, collection: str, vector_size: int = _DEFAULT_VECTOR_SIZE) -> None:
        existing = await self._client.get_collections()
        names = [c.name for c in existing.collections]
        if collection not in names:
            await self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            logger.info("qdrant_collection_created", collection=collection)
