"""Outbound port — QMetry test management integration."""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from aita.domain.models import TestResult


class QMetryPort(ABC):

    @abstractmethod
    async def push_results(self, run_id: UUID, results: list[TestResult]) -> str:
        """Push test results to QMetry. Returns execution key."""

    @abstractmethod
    async def create_test_cycle(self, name: str, service_name: str) -> str:
        """Create a new test cycle. Returns cycle key."""

    @abstractmethod
    async def get_project_key(self) -> str:
        """Return the configured QMetry project key."""
