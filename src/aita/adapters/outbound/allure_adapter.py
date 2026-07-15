"""Allure TestOps REST API adapter."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

import httpx
import structlog

from aita.domain.exceptions import AllureError
from aita.ports.outbound.allure_port import AllurePort

logger = structlog.get_logger()


class AllureAdapter(AllurePort):
    def __init__(self, server_url: str, project_id: str, api_token: str | None = None) -> None:
        self._base = server_url.rstrip("/")
        self._project = project_id
        self._headers = {"Authorization": f"Bearer {api_token}"} if api_token else {}

    async def upload_results(self, run_id: UUID, results_dir: Path) -> str:
        files = list(results_dir.glob("*"))
        if not files:
            logger.warning("allure_no_results", results_dir=str(results_dir))
            return self.get_report_url_sync(run_id)

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                multipart = [
                    ("files[]", (f.name, f.read_bytes(), "application/octet-stream"))
                    for f in files
                ]
                resp = await client.post(
                    f"{self._base}/allure-docker-service/send-results",
                    params={"project_id": self._project},
                    files=multipart,
                    headers=self._headers,
                )
                resp.raise_for_status()
                logger.info("allure_uploaded", run_id=str(run_id), files=len(files))
        except Exception as exc:
            raise AllureError(f"Allure upload failed: {exc}") from exc

        return await self.get_report_url(run_id)

    async def get_report_url(self, run_id: UUID) -> str:
        return f"{self._base}/allure-docker-service/projects/{self._project}/reports/latest/index.html"

    def get_report_url_sync(self, run_id: UUID) -> str:
        return f"{self._base}/allure-docker-service/projects/{self._project}/reports/latest/index.html"
