"""Step 8 — Persist healed tests to the test repository (bare git)."""
from __future__ import annotations

import structlog

from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.domain.enums import PipelineStep
from aita.ports.outbound.test_repo_port import TestRepoPort

logger = structlog.get_logger()


class PersistStep(BaseStep):
    def __init__(self, test_repo: TestRepoPort) -> None:
        self._repo = test_repo

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.PERSIST

    def should_skip(self, ctx: PipelineContext) -> bool:
        return not ctx.healed_tests

    async def _execute(self, ctx: PipelineContext) -> None:
        service = ctx.options.service_name
        saved = 0

        for op_id, test_case in ctx.healed_tests.items():
            fp = ctx.fingerprints.get(op_id)
            if fp:
                test_case.fingerprint_at_generation = fp.combined_hash

            git_ref = await self._repo.save(service, test_case)
            test_case.git_ref = git_ref
            saved += 1

        logger.info("persist_done", saved=saved, service=service)
