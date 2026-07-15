"""Inbound port — knowledge / RAG management."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from uuid import UUID


class KnowledgePort(ABC):

    @abstractmethod
    async def ingest(self, service_name: str, source_path: Path, doc_type: str | None = None) -> int:
        """Ingest a file or directory into the knowledge base. Returns chunk count."""

    @abstractmethod
    async def query(self, service_name: str, query: str, top_k: int = 5) -> list[str]:
        """Retrieve relevant snippets for a query."""

    @abstractmethod
    async def delete_service_knowledge(self, service_name: str) -> None:
        """Remove all knowledge vectors for a service."""
