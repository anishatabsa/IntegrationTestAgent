"""Step 5 — Enrich pipeline context with RAG knowledge."""
from __future__ import annotations

import structlog

from aita.core.knowledge.rag_engine import RAGEngine
from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.domain.enums import PipelineStep
from aita.domain.models import RAGContext

logger = structlog.get_logger()


class RAGEnrichStep(BaseStep):
    def __init__(self, rag_engine: RAGEngine) -> None:
        self._rag = rag_engine

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.RAG_ENRICH

    def should_skip(self, ctx: PipelineContext) -> bool:
        return not ctx.options.learn_from_kb or not ctx.changed_operations

    async def _execute(self, ctx: PipelineContext) -> None:
        service = ctx.options.service_name

        # Build a combined query from all changed operation summaries
        changed_eps = [e for e in ctx.endpoints if e.operation_id in ctx.changed_operations]
        query_parts = [f"{e.method} {e.path}: {e.summary}" for e in changed_eps]
        query = "; ".join(query_parts[:10])  # cap at 10 to keep tokens manageable

        logger.info("rag_enrich", service=service, query_len=len(query))
        rag_ctx = await self._rag.enrich(service_name=service, query=query)
        ctx.rag_context = rag_ctx

        logger.info(
            "rag_enrich_done",
            patterns=len(rag_ctx.patterns),
            snippets=len(rag_ctx.knowledge_snippets),
            feedback=len(rag_ctx.feedback_items),
        )
