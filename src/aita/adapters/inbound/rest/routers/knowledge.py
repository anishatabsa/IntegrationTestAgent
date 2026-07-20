"""REST router: /api/v1/knowledge — KB ingestion and query."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


# ── dependency helpers ────────────────────────────────────────────────────────

def _get_ingester(request: Request):
    try:
        return request.app.state.ingester
    except AttributeError:
        raise HTTPException(status_code=503, detail="Knowledge ingester not initialised")


def _get_rag_engine(request: Request):
    try:
        return request.app.state.rag_engine
    except AttributeError:
        raise HTTPException(status_code=503, detail="RAG engine not initialised")


def _get_vector_store(request: Request):
    try:
        return request.app.state.vector_store
    except AttributeError:
        raise HTTPException(status_code=503, detail="Vector store not initialised")


# ── request models ────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    service_name: str
    query: str
    top_k: int = 5


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/ingest/{service_name}")
async def ingest(
    service_name: str,
    file: UploadFile = File(...),
    doc_type: str = "markdown",
    ingester=Depends(_get_ingester),
):
    """Upload a document and ingest it into the knowledge base for *service_name*.

    Supports ``.md``, ``.txt``, ``.pdf``, and ``.rst`` files.
    Returns the number of chunks stored in the vector store.
    """
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in {".md", ".txt", ".pdf", ".rst"}:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix}'. Allowed: .md .txt .pdf .rst",
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="aita_kb_"))
    try:
        dest = tmp_dir / filename
        dest.write_bytes(await file.read())
        chunks = await ingester.ingest(dest, service_name, doc_type)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return {
        "service": service_name,
        "filename": filename,
        "chunks_ingested": chunks,
        "status": "ok",
    }


@router.post("/query")
async def query_kb(body: QueryRequest, rag_engine=Depends(_get_rag_engine)):
    """Semantic search over the knowledge base for a service."""
    rag_ctx = await rag_engine.enrich(service_name=body.service_name, query=body.query)
    return {
        "service": body.service_name,
        "query": body.query,
        "snippets": rag_ctx.knowledge_snippets[: body.top_k],
        "patterns": len(rag_ctx.patterns),
        "feedback_items": len(rag_ctx.feedback_items),
    }


@router.delete("/{service_name}")
async def delete_knowledge(
    service_name: str,
    vector_store=Depends(_get_vector_store),
):
    """Delete all knowledge vectors stored for *service_name*."""
    from aita.config import settings

    await vector_store.delete_by_filter(settings.qdrant_collection, "service", service_name)
    return {"deleted": True, "service": service_name}
