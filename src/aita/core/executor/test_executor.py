"""Base test executor interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from aita.domain.models import TestCase, TestResult


class TestExecutor(ABC):
    @abstractmethod
    async def run(
        self, tests: list[TestCase], base_url: str, run_id: UUID
    ) -> list[TestResult]:
        ...
