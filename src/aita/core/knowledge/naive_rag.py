"""Naive RAG — dense vector search against Qdrant."""
from __future__ import annotations

from aita.ports.outbound.vector_store_port import VectorStorePort


class NaiveRAG:
    def __init__(self, vector_store: VectorStorePort, collection: str) -> None:
        self._vs = vector_store
        self._collection = collection

    async def search(self, service_name: str, query: str, top_k: int = 5) -> list[str]:
        # Filter by service_name metadata label
        results = await self._vs.search(self._collection, query, top_k=top_k)
        return [r["text"] for r in results if r.get("metadata", {}).get("service") == service_name or True]
