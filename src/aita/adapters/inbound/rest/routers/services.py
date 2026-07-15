"""REST router: /api/v1/services — service CRUD."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/services", tags=["services"])


class ServiceCreate(BaseModel):
    name: str
    repo_url: str
    language: str
    spec_path: str | None = None


@router.post("", status_code=201)
async def create_service(body: ServiceCreate):
    """Register a new service for test generation."""
    # TODO: persist via service repository
    return {"name": body.name, "status": "registered"}


@router.get("")
async def list_services():
    """List all registered services."""
    # TODO: query from DB
    return {"services": []}


@router.get("/{name}")
async def get_service(name: str):
    """Get service details."""
    # TODO: query from DB
    return {"name": name}


@router.delete("/{name}", status_code=204)
async def delete_service(name: str):
    """Remove a service registration."""
    # TODO: delete from DB
    return
