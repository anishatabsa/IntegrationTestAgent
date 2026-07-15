"""Knowledge ingester — reads Markdown / PDF / Text files and upserts into Qdrant."""
from __future__ import annotations

from pathlib import Path

import structlog

from aita.ports.outbound.vector_store_port import VectorStorePort

logger = structlog.get_logger()

_SUPPORTED_EXTS = {".md", ".txt", ".pdf", ".rst"}
_CHUNK_SIZE = 1000
_CHUNK_OVERLAP = 100


def _chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping fixed-size chunks."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        start += size - overlap
    return chunks


def _read_file(path: Path) -> str:
    if path.suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            logger.warning("pypdf_not_installed", path=str(path))
            return ""
    return path.read_text(encoding="utf-8", errors="ignore")


class KnowledgeIngester:
    def __init__(self, vector_store: VectorStorePort, collection: str) -> None:
        self._vs = vector_store
        self._collection = collection

    async def ingest(self, source_path: Path, service_name: str, doc_type: str | None = None) -> int:
        """Ingest a file or directory. Returns number of chunks upserted."""
        paths = (
            [p for p in source_path.rglob("*") if p.is_file() and p.suffix in _SUPPORTED_EXTS]
            if source_path.is_dir()
            else [source_path] if source_path.suffix in _SUPPORTED_EXTS else []
        )

        total = 0
        for path in paths:
            text = _read_file(path)
            if not text.strip():
                continue

            chunks = _chunk_text(text)
            metadata = [
                {"service": service_name, "source": str(path), "doc_type": doc_type or path.suffix}
                for _ in chunks
            ]
            await self._vs.upsert(self._collection, chunks, metadata)
            total += len(chunks)
            logger.info("ingested", path=str(path), chunks=len(chunks))

        return total
