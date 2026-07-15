"""Step 1 — Clone / pull the service repository."""
from __future__ import annotations

from pathlib import Path

import structlog

from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.domain.enums import PipelineStep
from aita.domain.exceptions import GitError, PipelineStepError
from aita.ports.outbound.git_port import GitPort

logger = structlog.get_logger()


class GitPullStep(BaseStep):
    def __init__(self, git_port: GitPort, repos_base: Path) -> None:
        self._git = git_port
        self._repos_base = repos_base

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.GIT_PULL

    async def _execute(self, ctx: PipelineContext) -> None:
        service = ctx.options.service_name
        branch = ctx.options.branch
        repo_url = ctx.run.service.repo_url if ctx.run and ctx.run.service else ""

        if not repo_url:
            raise PipelineStepError(
                self.step_id, f"No repo_url configured for service '{service}'"
            )

        target_dir = self._repos_base / service
        target_dir.mkdir(parents=True, exist_ok=True)

        logger.info("git_pull", service=service, branch=branch, repo_url=repo_url)
        try:
            sha = await self._git.clone_or_pull(repo_url, target_dir, branch)
        except GitError as exc:
            raise PipelineStepError(self.step_id, str(exc), cause=exc) from exc

        ctx.repo_dir = target_dir
        ctx.commit_sha = sha
        logger.info("git_pull_done", sha=sha, path=str(target_dir))
