"""Outbound port — test repository (bare git per service)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from aita.domain.models import TestCase


class TestRepoPort(ABC):

    @abstractmethod
    async def load(self, service_name: str, operation_id: str) -> TestCase | None:
        """Return the persisted test case for an endpoint, or None."""

    @abstractmethod
    async def save(self, service_name: str, test_case: TestCase) -> str:
        """Persist / update a test case. Returns git commit SHA."""

    @abstractmethod
    async def delete(self, service_name: str, operation_id: str) -> None:
        """Remove a test case from the repository."""

    @abstractmethod
    async def list_operations(self, service_name: str) -> list[str]:
        """Return all operation_ids stored for a service."""
