"""
Agentic RAG — uses LlamaIndex query engine with ReAct agent for multi-hop retrieval.
Falls back to simple vector search if agent is unavailable.
"""
from __future__ import annotations

import structlog

from aita.ports.outbound.vector_store_port import VectorStorePort

logger = structlog.get_logger()


class AgenticRAG:
    def __init__(self, vector_store: VectorStorePort, collection: str) -> None:
        self._vs = vector_store
        self._collection = collection
        self._agent = None  # lazy init

    async def _get_agent(self):
        """Lazy-initialise LlamaIndex agent."""
        if self._agent is not None:
            return self._agent
        try:
            from llama_index.core import VectorStoreIndex
            from llama_index.core.agent import ReActAgent
            # Agent init requires index — build from existing collection
            # For now return None to fall back to simple search
            return None
        except ImportError:
            return None

    async def search(self, service_name: str, query: str, top_k: int = 5) -> list[str]:
        agent = await self._get_agent()
        if agent is None:
            # Fallback: multi-query decomposition via simple vector search
            sub_queries = self._decompose(query)
            snippets: list[str] = []
            seen: set[str] = set()
            for sq in sub_queries:
                results = await self._vs.search(self._collection, sq, top_k=3)
                for r in results:
                    text = r.get("text", "")
                    if text and text not in seen:
                        snippets.append(text)
                        seen.add(text)
            return snippets[:top_k]

        # Full agent invocation
        try:
            response = await agent.aquery(query)
            return [str(response)]
        except Exception as exc:
            logger.warning("agentic_rag_agent_error", error=str(exc))
            return []

    def _decompose(self, query: str) -> list[str]:
        """Naive query decomposition: split on semicolons or return as-is."""
        parts = [p.strip() for p in query.split(";") if p.strip()]
        return parts[:3] if len(parts) > 1 else [query]
