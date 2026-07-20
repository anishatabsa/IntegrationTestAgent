"""Step 9 — Execute the test suite against the live Docker service."""
from __future__ import annotations

import structlog

from aita.core.executor.test_executor import TestExecutor
from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.domain.enums import PipelineStep
from aita.ports.outbound.docker_port import DockerPort

logger = structlog.get_logger()


class ExecuteStep(BaseStep):
    def __init__(self, executor: TestExecutor, docker: DockerPort) -> None:
        self._executor = executor
        self._docker = docker

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.EXECUTE

    def should_skip(self, ctx: PipelineContext) -> bool:
        return not ctx.options.run_tests or not ctx.healed_tests

    async def _execute(self, ctx: PipelineContext) -> None:
        service = ctx.options.service_name

        # Use explicit base_url from options (local / non-Docker services) when available
        base_url = ctx.options.base_url
        if not base_url:
            container = await self._docker.find_container(service)
            if container is None:
                ctx.warn(
                    f"No running container found for '{service}' and no base_url set; "
                    "skipping test execution. Pass base_url in the run request."
                )
                return
            base_url = await self._docker.get_base_url(container)

        healthy = await self._docker.health_check(base_url)
        if not healthy:
            ctx.warn(f"Service '{service}' at {base_url} failed health check; skipping execution.")
            return

        logger.info("execute", service=service, base_url=base_url)
        tests_list = list(ctx.healed_tests.values())
        logger.info("execute_test_count", count=len(tests_list))
        results = await self._executor.run(
            tests=tests_list,
            base_url=base_url,
            run_id=ctx.run_id,
        )
        ctx.test_results = results
        passing = sum(1 for r in results if r.status == "passed")
        logger.info("execute_done", total=len(results), passing=passing)
        if not results:
            ctx.warn(
                f"pytest produced 0 results for {len(tests_list)} test(s). "
                "Check ~/.aita_pytest_debug.txt for full pytest output."
            )
