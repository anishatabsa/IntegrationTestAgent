"""Step 8 — Fingerprint healed tests and mark them ready for publishing.

Tests are kept in ctx.healed_tests (in memory).  PublishStep (step 13) is
responsible for pushing them to the GitHub test-automation repository.
No files are written to the working directory here.
"""
from __future__ import annotations

import structlog

from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.domain.enums import PipelineStep

logger = structlog.get_logger()


class PersistStep(BaseStep):
    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.PERSIST

    def should_skip(self, ctx: PipelineContext) -> bool:
        return not ctx.healed_tests

    async def _execute(self, ctx: PipelineContext) -> None:
        from aita.core.pipeline.steps.publish_step import _merge_test_content

        merged_count = 0
        for op_id, test_case in ctx.healed_tests.items():
            fp = ctx.fingerprints.get(op_id)
            if fp:
                test_case.fingerprint_at_generation = fp.combined_hash

            # Merge with existing content before execution.
            # When FetchExistingTestsStep is active the LLM generates in improvement
            # mode — it may produce a complete revised file, or a partial patch.
            # Either way, merging here ensures ExecuteStep runs a complete, valid
            # test file (not raw LLM output that might be missing setUp / helpers).
            if op_id in ctx.existing_tests:
                merged = _merge_test_content(ctx.existing_tests[op_id], test_case.content)
                test_case.content = merged
                merged_count += 1

            # git_ref will be updated by PublishStep once the PR is created
            test_case.git_ref = "pending"

        logger.info("persist_done", count=len(ctx.healed_tests), merged=merged_count)
