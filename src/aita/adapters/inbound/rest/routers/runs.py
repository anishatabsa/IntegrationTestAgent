"""REST router: /api/v1/runs — pipeline trigger and status."""
from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from aita.core.pipeline.context import PipelineContext, PipelineOptions
from aita.core.orchestrator import PipelineOrchestrator
from aita.domain.enums import RunStatus

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


class RunRequest(BaseModel):
    service_name: str
    branch: str = "main"
    force_generate: bool = False
    ignore_cache: bool = False
    learn_from_kb: bool = True
    update_kb: bool = False
    selected_operations: list[str] = []
    run_tests: bool = True
    push_to_allure: bool = False
    push_to_qmetry: bool = False
    # Inline service config — no pre-registration needed when these are set
    repo_url: str = ""
    base_url: str = ""
    language: str = "python"
    spec_url: str = ""
    # Test automation repo publishing
    test_automation_repo_url: str = ""
    test_automation_branch: str = "main"
    publish_on_gate_pass: bool = True


def get_orchestrator() -> PipelineOrchestrator:
    # Injected via app.state in main.py
    from aita.main import app
    return app.state.orchestrator


@router.post("", status_code=202)
async def trigger_run(
    req: RunRequest,
    background_tasks: BackgroundTasks,
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
):
    """Trigger a pipeline run asynchronously. Returns run_id immediately."""
    options = PipelineOptions(**req.model_dump())
    ctx = PipelineContext(options=options)
    # Pre-register so the SSE stream can find this run_id immediately
    orchestrator.register_run(ctx)
    background_tasks.add_task(orchestrator.run, req.service_name, options, ctx)
    return {"run_id": str(ctx.run_id), "status": "accepted"}


@router.get("/{run_id}/stream")
async def stream_run(
    run_id: UUID,
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
):
    """SSE endpoint: poll the running pipeline context and emit step events."""

    async def event_generator():
        # Wait up to 4 seconds for the background task to actually start
        ctx: PipelineContext | None = None
        for _ in range(20):
            ctx = await orchestrator.get_run(run_id)
            if ctx is not None:
                break
            await asyncio.sleep(0.2)

        if ctx is None:
            yield f"data: {json.dumps({'event_type': 'error', 'message': 'Run not found'})}\n\n"
            return

        last_idx = 0
        last_status = None

        while True:
            # Emit any newly completed steps
            while last_idx < len(ctx.step_results):
                r = ctx.step_results[last_idx]
                event_type = "step_completed" if r.status == "success" else (
                    "step_failed" if r.status == "failed" else "step_skipped"
                )
                payload = {
                    "event_type": event_type,
                    "step": str(r.step),
                    "message": r.message or str(r.step),
                    "duration_ms": r.duration_ms,
                }
                yield f"data: {json.dumps(payload)}\n\n"
                last_idx += 1

            current_status = ctx.status
            if current_status != last_status:
                last_status = current_status

            # Pipeline finished
            if current_status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
                if current_status == RunStatus.COMPLETED:
                    yield f"data: {json.dumps({'event_type': 'pipeline_completed', 'data': ctx.summary()})}\n\n"
                else:
                    errors = "; ".join(ctx.errors) or str(current_status)
                    # Include the run summary so the CLI can display pass rate etc.
                    yield f"data: {json.dumps({'event_type': 'pipeline_failed', 'message': errors, 'data': ctx.summary()})}\n\n"
                return

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{run_id}")
async def get_run(
    run_id: UUID,
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
):
    ctx = await orchestrator.get_run(run_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Run not found")
    return ctx.summary()
