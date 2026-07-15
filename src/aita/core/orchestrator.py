"""
Pipeline orchestrator — implements PipelinePort (inbound) using the Template Method
pattern. Steps are fixed in order; each is a pluggable BaseStep implementation.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import AsyncIterator
from uuid import UUID

import structlog

from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext, PipelineOptions
from aita.core.pipeline.events import (
    pipeline_completed,
    pipeline_failed,
    step_completed,
    step_failed,
    step_started,
)
from aita.domain.enums import RunStatus
from aita.domain.exceptions import PipelineStepError
from aita.ports.inbound.pipeline_port import PipelinePort
from aita.ports.outbound.cache_port import CachePort

logger = structlog.get_logger()

_RUN_STATUS_KEY = "run:{run_id}:status"
_RUN_EVENTS_KEY = "run:{run_id}:events"


class PipelineOrchestrator(PipelinePort):
    """
    Runs the 12-step pipeline in order.
    Non-critical step failures are caught and logged as warnings.
    Critical step failures (git_pull, spec_parse) abort the run.
    """

    CRITICAL_STEPS = {"git_pull", "spec_parse"}

    def __init__(self, steps: list[BaseStep], cache: CachePort) -> None:
        self._steps = steps
        self._cache = cache
        self._active_runs: dict[UUID, PipelineContext] = {}

    async def run(self, service_name: str, options: PipelineOptions) -> PipelineContext:
        ctx = PipelineContext(options=options)
        self._active_runs[ctx.run_id] = ctx
        ctx.started_at = datetime.now(timezone.utc)
        ctx.status = RunStatus.RUNNING

        logger.info("pipeline_started", run_id=str(ctx.run_id), service=service_name)

        try:
            for step in self._steps:
                await self._run_step(step, ctx)
                if ctx.status == RunStatus.FAILED and step.step_id in self.CRITICAL_STEPS:
                    break
        except Exception as exc:
            ctx.fail(str(exc))
        finally:
            ctx.finished_at = datetime.now(timezone.utc)
            if ctx.status == RunStatus.RUNNING:
                ctx.status = RunStatus.COMPLETED
            self._active_runs.pop(ctx.run_id, None)

        logger.info("pipeline_finished", run_id=str(ctx.run_id), status=ctx.status)
        return ctx

    async def run_streaming(
        self, service_name: str, options: PipelineOptions
    ) -> AsyncIterator[dict]:
        ctx = PipelineContext(options=options)
        self._active_runs[ctx.run_id] = ctx
        ctx.started_at = datetime.now(timezone.utc)
        ctx.status = RunStatus.RUNNING

        # We run in a background task and yield events via an asyncio.Queue
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def _run_with_events() -> None:
            try:
                for step in self._steps:
                    event = step_started(ctx.run_id, step.step_id)
                    await queue.put({"sse": event.to_sse(), "data": event.__dict__})

                    try:
                        await step.run(ctx)
                        event = step_completed(ctx.run_id, step.step_id)
                    except PipelineStepError as exc:
                        event = step_failed(ctx.run_id, step.step_id, str(exc))
                        await queue.put({"sse": event.to_sse(), "data": event.__dict__})
                        if step.step_id in self.CRITICAL_STEPS:
                            break
                        continue

                    await queue.put({"sse": event.to_sse(), "data": event.__dict__})

                summary = ctx.summary()
                if ctx.status == RunStatus.RUNNING:
                    ctx.status = RunStatus.COMPLETED
                final = pipeline_completed(ctx.run_id, summary)
                await queue.put({"sse": final.to_sse(), "data": final.__dict__})
            except Exception as exc:
                ctx.fail(str(exc))
                event = pipeline_failed(ctx.run_id, str(exc))
                await queue.put({"sse": event.to_sse(), "data": event.__dict__})
            finally:
                ctx.finished_at = datetime.now(timezone.utc)
                self._active_runs.pop(ctx.run_id, None)
                await queue.put(None)  # sentinel

        asyncio.create_task(_run_with_events())

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    async def get_run(self, run_id: UUID) -> PipelineContext | None:
        return self._active_runs.get(run_id)

    async def cancel_run(self, run_id: UUID) -> bool:
        ctx = self._active_runs.get(run_id)
        if ctx:
            ctx.status = RunStatus.CANCELLED
            return True
        return False

    async def _run_step(self, step: BaseStep, ctx: PipelineContext) -> None:
        try:
            await step.run(ctx)
        except PipelineStepError as exc:
            if step.step_id in self.CRITICAL_STEPS:
                ctx.fail(str(exc))
            else:
                ctx.warn(f"Non-critical step '{step.step_id}' failed: {exc}")
