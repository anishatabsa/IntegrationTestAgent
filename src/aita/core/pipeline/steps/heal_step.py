"""Step 7 — Run the 5-stage healer on generated tests."""
from __future__ import annotations

import structlog

from aita.core.healer.healer import HealerPipeline
from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.domain.enums import PipelineStep, TestStatus

logger = structlog.get_logger()


class HealStep(BaseStep):
    def __init__(self, healer: HealerPipeline) -> None:
        self._healer = healer

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.HEAL

    def should_skip(self, ctx: PipelineContext) -> bool:
        return not ctx.generated_tests

    async def _execute(self, ctx: PipelineContext) -> None:
        total_tokens = 0
        healed_count = 0
        dropped: list[str] = []

        for op_id, test_case in ctx.generated_tests.items():
            result = await self._healer.heal(test_case)

            if result.dropped:
                dropped.append(op_id)
                # Create feedback for dropped test
                from aita.domain.enums import FeedbackSource, FeedbackType
                from aita.domain.models import FeedbackItem
                ctx.feedback_items.append(FeedbackItem(
                    source=FeedbackSource.AUTO,
                    feedback_type=FeedbackType.COMPILATION_ERROR,
                    description=f"Test dropped after healer exhausted all repair attempts: {result.error}",
                    endpoint_id=None,
                ))
                logger.warning("test_dropped", operation_id=op_id, error=result.error)
            else:
                test_case.content = result.content
                test_case.status = TestStatus.HEALED if result.was_modified else TestStatus.GENERATED
                ctx.healed_tests[op_id] = test_case
                if result.was_modified:
                    healed_count += 1

            total_tokens += result.tokens_used

        ctx.token_usage[PipelineStep.HEAL] = total_tokens
        logger.info(
            "heal_done",
            healed=healed_count,
            dropped=len(dropped),
            tokens=total_tokens,
        )
