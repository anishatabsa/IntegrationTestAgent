"""Step 12 — Quality gate: fail the run if pass rate is below threshold."""
from __future__ import annotations

import structlog

from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.domain.enums import PipelineStep, RunStatus

logger = structlog.get_logger()

DEFAULT_PASS_THRESHOLD = 80.0  # percent


class GateStep(BaseStep):
    def __init__(self, pass_threshold: float = DEFAULT_PASS_THRESHOLD) -> None:
        self._threshold = pass_threshold

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.GATE

    def should_skip(self, ctx: PipelineContext) -> bool:
        return not ctx.test_results

    async def _execute(self, ctx: PipelineContext) -> None:
        summary = ctx.summary()
        pass_rate = summary["pass_rate"]
        total = summary["tests_total"]

        logger.info("gate_check", pass_rate=pass_rate, threshold=self._threshold, total=total)

        if pass_rate < self._threshold:
            msg = (
                f"Quality gate FAILED: {pass_rate:.1f}% pass rate "
                f"(threshold {self._threshold:.0f}%)"
            )
            ctx.status = RunStatus.FAILED
            ctx.errors.append(msg)
            logger.warning("gate_failed", pass_rate=pass_rate)
        else:
            ctx.status = RunStatus.COMPLETED
            logger.info("gate_passed", pass_rate=pass_rate)
