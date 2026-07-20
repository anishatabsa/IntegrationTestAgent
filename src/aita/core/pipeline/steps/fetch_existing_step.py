"""Step 5b — Fetch existing test files from the automation repo before generation.

Populates ctx.existing_tests[op_id] with the current file content for each
changed operation that already has a test file on the automation repo branch.

This content is injected into the LLM prompt so the model can IMPROVE the
existing test suite rather than generating blindly from scratch. The key
benefit: a method that was correct in a previous run won't be silently
downgraded if the LLM rewrites it with fewer assertions.

Skip conditions
---------------
- No test automation repo URL configured.
- No GitHub token set.
- No changed operations to fetch for.

Any exception is caught and stored as a warning — a fetch failure must never
block test generation.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import structlog

from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.domain.enums import PipelineStep

logger = structlog.get_logger()


class FetchExistingTestsStep(BaseStep):
    """Fetch existing test files from GitHub to provide the LLM with improvement context."""

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.FETCH_EXISTING

    def should_skip(self, ctx: PipelineContext) -> bool:
        from aita.config import settings

        repo_url = ctx.options.test_automation_repo_url or settings.test_automation_repo_url
        token = settings.github_token
        if not repo_url:
            logger.info("fetch_existing_skipped", reason="no_repo_url")
            return True
        if not token:
            logger.info("fetch_existing_skipped", reason="no_github_token")
            return True
        if not ctx.changed_operations:
            logger.info("fetch_existing_skipped", reason="no_changed_operations")
            return True
        return False

    async def _execute(self, ctx: PipelineContext) -> None:
        try:
            await asyncio.to_thread(self._fetch_sync, ctx)
        except Exception as exc:
            logger.warning("fetch_existing_error", error=str(exc), exc_info=True)
            ctx.warn(f"FetchExistingTestsStep: {exc}")

    def _fetch_sync(self, ctx: PipelineContext) -> None:
        from github import Github, GithubException
        from aita.config import settings
        from aita.core.pipeline.steps.publish_step import (
            _parse_github_owner_repo,
            _file_path_in_repo,
        )

        token = settings.github_token
        repo_url = ctx.options.test_automation_repo_url or settings.test_automation_repo_url

        parsed = _parse_github_owner_repo(repo_url)
        if not parsed:
            logger.warning("fetch_existing_bad_url", url=repo_url)
            return

        owner, repo_name = parsed
        gh = Github(token)
        try:
            repo = gh.get_repo(f"{owner}/{repo_name}")
        except GithubException as exc:
            logger.warning("fetch_existing_repo_error", repo=f"{owner}/{repo_name}", error=str(exc))
            return

        service = ctx.options.service_name
        branch_name = f"aita/{service}"
        language = ctx.options.language or "python"

        fetched = 0
        for op_id in ctx.changed_operations:
            # Derive file path the same way PublishStep does — reuse the helper.
            fake_tc = SimpleNamespace(
                name=f"test_{op_id}",
                language=language,
            )
            file_path = _file_path_in_repo(service, fake_tc)
            try:
                contents = repo.get_contents(file_path, ref=branch_name)
                existing_content = contents.decoded_content.decode("utf-8", errors="ignore")
                ctx.existing_tests[op_id] = existing_content
                fetched += 1
                logger.info(
                    "fetch_existing_found",
                    op_id=op_id,
                    path=file_path,
                    bytes=len(existing_content),
                )
            except GithubException:
                # File doesn't exist yet — first-time generation, nothing to fetch.
                logger.debug("fetch_existing_not_found", op_id=op_id, path=file_path)

        logger.info(
            "fetch_existing_done",
            fetched=fetched,
            total=len(ctx.changed_operations),
            service=service,
        )
