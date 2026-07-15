"""Base class for all pipeline steps (Template Method pattern)."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

import structlog

from aita.core.pipeline.context import PipelineContext, StepResult
from aita.core.pipeline.events import step_completed, step_failed, step_started
from aita.domain.enums import PipelineStep
from aita.domain.exceptions import PipelineStepError

logger = structlog.get_logger()


class BaseStep(ABC):
    """
    Each concrete step:
    1. Declares its step name via `step_id` property
    2. Implements `_execute(ctx)` with actual logic
    3. Can override `should_skip(ctx)` to short-circuit
    """

    @property
    @abstractmethod
    def step_id(self) -> PipelineStep:
        ...

    def should_skip(self, ctx: PipelineContext) -> bool:  # noqa: ARG002
        return False

    @abstractmethod
    async def _execute(self, ctx: PipelineContext) -> None:
        ...

    async def run(self, ctx: PipelineContext) -> StepResult:
        log = logger.bind(step=self.step_id, run_id=str(ctx.run_id))

        if self.should_skip(ctx):
            result = StepResult(step=self.step_id, status="skipped", message="Step skipped")
            ctx.add_step_result(result)
            log.info("step_skipped")
            return result

        log.info("step_started")
        t0 = time.monotonic()
        try:
            await self._execute(ctx)
            duration_ms = int((time.monotonic() - t0) * 1000)
            result = StepResult(
                step=self.step_id,
                status="success",
                duration_ms=duration_ms,
            )
            ctx.add_step_result(result)
            log.info("step_completed", duration_ms=duration_ms)
            return result

        except PipelineStepError:
            raise
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            msg = str(exc)
            log.error("step_failed", error=msg, duration_ms=duration_ms)
            result = StepResult(
                step=self.step_id,
                status="failed",
                message=msg,
                duration_ms=duration_ms,
            )
            ctx.add_step_result(result)
            raise PipelineStepError(step=self.step_id, message=msg, cause=exc) from exc
