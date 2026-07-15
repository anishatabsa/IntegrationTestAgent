"""Outbound port — Allure TestOps integration."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from uuid import UUID


class AllurePort(ABC):

    @abstractmethod
    async def upload_results(self, run_id: UUID, results_dir: Path) -> str:
        """Upload Allure result files. Returns report URL."""

    @abstractmethod
    async def get_report_url(self, run_id: UUID) -> str:
        """Return the URL to the generated report."""
