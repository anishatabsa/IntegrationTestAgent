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

    def should_skip(self, ctx: PipelineContext) -> bool:
        repo_url = ctx.options.repo_url or (
            ctx.run.service.repo_url if ctx.run and ctx.run.service else ""
        )
        spec_url = ctx.options.spec_url or ctx.options.base_url
        # When the source repo is on GitHub AND the spec comes from the live service,
        # we can skip the local clone entirely — source scanning uses the GitHub API
        # and the spec is fetched over HTTP by SpecParseStep.
        if repo_url.startswith("https://github.com/") and spec_url:
            logger.info("git_pull_skipped_github_api_mode", repo_url=repo_url)
            return True
        return False

    async def _execute(self, ctx: PipelineContext) -> None:
        service = ctx.options.service_name
        branch = ctx.options.branch

        # Prefer inline options (no service registry needed), fall back to DB record
        repo_url = ctx.options.repo_url or (
            ctx.run.service.repo_url if ctx.run and ctx.run.service else ""
        )

        if not repo_url:
            raise PipelineStepError(
                self.step_id,
                f"No repo_url for service '{service}'. "
                "Pass repo_url in the run request or pre-register the service."
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
