"""Step 6 — Generate test cases via LLM for changed endpoints."""
from __future__ import annotations

import structlog

from aita.core.generator.test_generator import TestGenerator
from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.domain.enums import PipelineStep

logger = structlog.get_logger()


class GenerateStep(BaseStep):
    def __init__(self, generator: TestGenerator) -> None:
        self._gen = generator

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.GENERATE

    def should_skip(self, ctx: PipelineContext) -> bool:
        return not ctx.changed_operations

    async def _execute(self, ctx: PipelineContext) -> None:
        service = ctx.options.service_name
        language = (
            ctx.options.language
            or (ctx.run.service.language if ctx.run and ctx.run.service else "python")
        )
        total_tokens = 0

        changed_eps = [e for e in ctx.endpoints if e.operation_id in ctx.changed_operations]
        logger.info("generate", service=service, count=len(changed_eps))

        for ep in changed_eps:
            scanned = next(
                (c for c in ctx.scanned_components if c.operation_id == ep.operation_id), None
            )
            fp = ctx.fingerprints.get(ep.operation_id)
            rag_ctx = ctx.rag_context

            existing_content = ctx.existing_tests.get(ep.operation_id)
            if existing_content:
                logger.info(
                    "generate_improvement_mode",
                    op_id=ep.operation_id,
                    existing_bytes=len(existing_content),
                )

            test_case, tokens = await self._gen.generate(
                endpoint=ep,
                scanned=scanned,
                fingerprint=fp,
                rag_context=rag_ctx,
                language=language,
                ignore_cache=ctx.options.ignore_cache,
                existing_content=existing_content,
            )
            ctx.generated_tests[ep.operation_id] = test_case
            total_tokens += tokens

        ctx.token_usage[PipelineStep.GENERATE] = total_tokens
        logger.info("generate_done", count=len(ctx.generated_tests), tokens=total_tokens)
