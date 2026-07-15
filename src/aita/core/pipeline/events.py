"""SSE event schema for real-time pipeline progress streaming."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from aita.domain.enums import PipelineStep


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PipelineEvent:
    event_type: str
    run_id: str
    step: str | None = None
    message: str = ""
    data: dict[str, Any] | None = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = _now_iso()

    def to_sse(self) -> str:
        payload = json.dumps(asdict(self))
        return f"event: {self.event_type}\ndata: {payload}\n\n"


def step_started(run_id: UUID, step: PipelineStep, message: str = "") -> PipelineEvent:
    return PipelineEvent(
        event_type="step_started",
        run_id=str(run_id),
        step=step,
        message=message or f"Starting {step}",
    )


def step_completed(
    run_id: UUID, step: PipelineStep, message: str = "", data: dict | None = None
) -> PipelineEvent:
    return PipelineEvent(
        event_type="step_completed",
        run_id=str(run_id),
        step=step,
        message=message or f"Completed {step}",
        data=data,
    )


def step_failed(run_id: UUID, step: PipelineStep, error: str) -> PipelineEvent:
    return PipelineEvent(
        event_type="step_failed",
        run_id=str(run_id),
        step=step,
        message=error,
    )


def pipeline_completed(run_id: UUID, summary: dict) -> PipelineEvent:
    return PipelineEvent(
        event_type="pipeline_completed",
        run_id=str(run_id),
        message="Pipeline finished",
        data=summary,
    )


def pipeline_failed(run_id: UUID, error: str) -> PipelineEvent:
    return PipelineEvent(
        event_type="pipeline_failed",
        run_id=str(run_id),
        message=error,
    )


def progress(run_id: UUID, message: str, data: dict | None = None) -> PipelineEvent:
    return PipelineEvent(
        event_type="progress",
        run_id=str(run_id),
        message=message,
        data=data,
    )
