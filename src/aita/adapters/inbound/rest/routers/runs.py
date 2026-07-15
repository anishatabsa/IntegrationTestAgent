"""REST router: /api/v1/runs — pipeline trigger and status."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from aita.core.pipeline.context import PipelineOptions
from aita.core.orchestrator import PipelineOrchestrator

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
    from aita.core.pipeline.context import PipelineContext
    import uuid
    options = PipelineOptions(**req.model_dump())
    ctx = PipelineContext(options=options)

    background_tasks.add_task(orchestrator.run, req.service_name, options)
    return {"run_id": str(ctx.run_id), "status": "accepted"}


@router.get("/{run_id}/stream")
async def stream_run(
    run_id: UUID,
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
):
    """SSE endpoint: streams pipeline events for a run."""
    async def event_generator():
        ctx = await orchestrator.get_run(run_id)
        if not ctx:
            yield "event: error\ndata: {\"message\": \"Run not found\"}\n\n"
            return
        # For fresh runs started via the stream endpoint
        options = ctx.options
        async for event in orchestrator.run_streaming(options.service_name, options):
            yield event.get("sse", "")

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
