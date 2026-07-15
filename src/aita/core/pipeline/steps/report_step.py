"""Step 11 — Push results to Allure and QMetry."""
from __future__ import annotations

from pathlib import Path

import structlog

from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.domain.enums import PipelineStep
from aita.ports.outbound.allure_port import AllurePort
from aita.ports.outbound.qmetry_port import QMetryPort

logger = structlog.get_logger()


class ReportStep(BaseStep):
    def __init__(
        self,
        allure: AllurePort,
        qmetry: QMetryPort,
        allure_results_dir: Path,
    ) -> None:
        self._allure = allure
        self._qmetry = qmetry
        self._results_dir = allure_results_dir

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.REPORT

    async def _execute(self, ctx: PipelineContext) -> None:
        if ctx.options.push_to_allure and ctx.test_results:
            try:
                url = await self._allure.upload_results(ctx.run_id, self._results_dir)
                ctx.allure_report_url = url
                logger.info("allure_report_uploaded", url=url)
            except Exception as exc:
                ctx.warn(f"Allure upload failed: {exc}")

        if ctx.options.push_to_qmetry and ctx.test_results:
            try:
                cycle_key = await self._qmetry.push_results(ctx.run_id, ctx.test_results)
                ctx.qmetry_cycle_key = cycle_key
                logger.info("qmetry_results_pushed", cycle_key=cycle_key)
            except Exception as exc:
                ctx.warn(f"QMetry push failed: {exc}")
