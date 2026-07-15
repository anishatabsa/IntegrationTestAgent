"""Step 3 — Scan source code for testable components."""
from __future__ import annotations

import structlog

from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.core.scanner.source_scanner import SourceScannerRegistry
from aita.domain.enums import PipelineStep

logger = structlog.get_logger()


class SourceScanStep(BaseStep):
    def __init__(self, scanner_registry: SourceScannerRegistry) -> None:
        self._registry = scanner_registry

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.SOURCE_SCAN

    def should_skip(self, ctx: PipelineContext) -> bool:
        return ctx.repo_dir is None

    async def _execute(self, ctx: PipelineContext) -> None:
        repo_dir = ctx.repo_dir
        language = ctx.run.service.language if ctx.run and ctx.run.service else None

        scanner = self._registry.get(language)
        if scanner is None:
            ctx.warn(f"No source scanner available for language '{language}'; skipping.")
            return

        logger.info("source_scan", language=language)
        components = await scanner.scan(repo_dir)
        ctx.scanned_components = components
        logger.info("source_scan_done", component_count=len(components))
