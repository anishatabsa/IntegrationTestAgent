"""Step 10 — Collect feedback from test results and store learned patterns."""
from __future__ import annotations

import structlog

from aita.core.feedback.collector import FeedbackCollector
from aita.core.feedback.pattern_learner import PatternLearner
from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.domain.enums import PipelineStep

logger = structlog.get_logger()


class FeedbackStep(BaseStep):
    def __init__(
        self,
        collector: FeedbackCollector,
        learner: PatternLearner,
        pattern_sink=None,  # InMemoryPatternStore | None
    ) -> None:
        self._collector = collector
        self._learner = learner
        self._sink = pattern_sink

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.FEEDBACK

    async def _execute(self, ctx: PipelineContext) -> None:
        service = ctx.options.service_name

        # Auto-generate feedback from failing test results
        auto_feedback = await self._collector.from_results(
            run_id=ctx.run_id,
            results=ctx.test_results,
            tests=ctx.healed_tests,
        )
        ctx.feedback_items.extend(auto_feedback)

        # Distill feedback into reusable learned patterns
        new_patterns = await self._learner.learn(
            service_name=service,
            feedback_items=ctx.feedback_items,
        )
        ctx.learned_patterns = new_patterns

        # Persist into the in-memory pattern store so the next pipeline run's
        # RAGEnrichStep will surface these patterns and feedback to the LLM.
        if self._sink is not None:
            self._sink.save(service, new_patterns, ctx.feedback_items)

        logger.info(
            "feedback_done",
            feedback_count=len(ctx.feedback_items),
            patterns_learned=len(new_patterns),
        )
