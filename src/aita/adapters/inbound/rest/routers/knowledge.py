"""REST router: /api/v1/knowledge — KB ingestion and query."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


class QueryRequest(BaseModel):
    service_name: str
    query: str
    top_k: int = 5


@router.post("/ingest/{service_name}", status_code=202)
async def ingest(service_name: str, file: UploadFile = File(...)):
    """Ingest a document into the knowledge base for a service."""
    # TODO: save file, call KnowledgeIngester
    return {"service": service_name, "filename": file.filename, "status": "queued"}


@router.post("/query")
async def query_kb(body: QueryRequest):
    """Query the knowledge base."""
    # TODO: call RAGEngine.enrich
    return {"snippets": []}


@router.delete("/{service_name}", status_code=204)
async def delete_knowledge(service_name: str):
    """Delete all knowledge vectors for a service."""
    # TODO: call VectorStorePort.delete
    return
