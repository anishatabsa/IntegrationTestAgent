"""Celery worker — async task queue for long-running pipeline runs."""
from __future__ import annotations

from celery import Celery

from aita.config import settings

celery_app = Celery(
    "aita",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="aita.run_pipeline", bind=True)
def run_pipeline_task(self, service_name: str, options: dict) -> dict:
    """Celery task wrapper for async pipeline runs."""
    import asyncio
    from aita.core.pipeline.context import PipelineOptions
    from aita.main import app as fastapi_app

    async def _run():
        orchestrator = fastapi_app.state.orchestrator
        opts = PipelineOptions(**options)
        ctx = await orchestrator.run(service_name, opts)
        return ctx.summary()

    return asyncio.run(_run())
