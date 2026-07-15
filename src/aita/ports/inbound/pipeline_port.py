"""Inbound port — driving side entry point for pipeline execution."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator
from uuid import UUID

from aita.core.pipeline.context import PipelineContext, PipelineOptions


class PipelinePort(ABC):
    """Primary port: anything that wants to trigger a pipeline implements against this."""

    @abstractmethod
    async def run(
        self, service_name: str, options: PipelineOptions
    ) -> PipelineContext:
        """Execute a full pipeline run and return the completed context."""

    @abstractmethod
    async def run_streaming(
        self, service_name: str, options: PipelineOptions
    ) -> AsyncIterator[dict]:
        """Execute a pipeline and yield SSE-compatible event dicts as steps complete."""

    @abstractmethod
    async def get_run(self, run_id: UUID) -> PipelineContext | None:
        """Retrieve a run context by ID (for polling-based clients)."""

    @abstractmethod
    async def cancel_run(self, run_id: UUID) -> bool:
        """Request cancellation of an in-progress run."""
