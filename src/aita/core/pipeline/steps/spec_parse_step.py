"""Step 2 — Parse service specification (OpenAPI / Swagger / Proto)."""
from __future__ import annotations

import structlog

from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.core.spec.parser import SpecParserRegistry
from aita.domain.enums import PipelineStep
from aita.domain.exceptions import PipelineStepError, SpecNotFoundError

logger = structlog.get_logger()


class SpecParseStep(BaseStep):
    def __init__(self, parser_registry: SpecParserRegistry) -> None:
        self._registry = parser_registry

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.SPEC_PARSE

    def should_skip(self, ctx: PipelineContext) -> bool:
        return ctx.repo_dir is None

    async def _execute(self, ctx: PipelineContext) -> None:
        repo_dir = ctx.repo_dir
        service = ctx.options.service_name

        try:
            parser = self._registry.detect(repo_dir)
        except SpecNotFoundError as exc:
            raise PipelineStepError(self.step_id, str(exc), cause=exc) from exc

        logger.info("spec_parse", format=parser.spec_format, service=service)
        endpoints = await parser.parse(repo_dir)

        ctx.endpoints = endpoints
        logger.info("spec_parse_done", endpoint_count=len(endpoints))
