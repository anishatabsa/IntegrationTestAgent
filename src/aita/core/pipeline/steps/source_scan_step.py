"""Step 3 — Scan source code for testable components."""
from __future__ import annotations

import os
import structlog

from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.core.scanner.source_scanner import SourceScannerRegistry
from aita.domain.enums import PipelineStep

logger = structlog.get_logger()


def _is_github_url(url: str) -> bool:
    return bool(url) and url.startswith("https://github.com/")


class SourceScanStep(BaseStep):
    def __init__(self, scanner_registry: SourceScannerRegistry) -> None:
        self._registry = scanner_registry

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.SOURCE_SCAN

    def should_skip(self, ctx: PipelineContext) -> bool:
        # Run if we have either a local clone OR a GitHub URL to scan via API
        has_local = ctx.repo_dir is not None
        has_github = _is_github_url(ctx.options.repo_url)
        return not (has_local or has_github)

    async def _execute(self, ctx: PipelineContext) -> None:
        language = ctx.options.language or (
            ctx.run.service.language if ctx.run and ctx.run.service else None
        )

        scanner = self._registry.get(language)
        if scanner is None:
            ctx.warn(f"No source scanner available for language '{language}'; skipping.")
            return

        if ctx.repo_dir is not None:
            # Local filesystem scan (e.g. during development or when git clone ran)
            logger.info("source_scan", language=language, mode="local")
            components = await scanner.scan(ctx.repo_dir)
        elif _is_github_url(ctx.options.repo_url):
            # GitHub API scan — no local clone needed
            from aita.config import settings as _settings
            token = os.environ.get("GITHUB_TOKEN") or _settings.github_token
            if not token:
                ctx.warn("GITHUB_TOKEN not set — skipping source scan")
                return
            branch = ctx.options.branch or "main"
            logger.info(
                "source_scan",
                language=language,
                mode="github",
                repo=ctx.options.repo_url,
                branch=branch,
            )
            components = await scanner.scan_from_github(ctx.options.repo_url, token, branch)
        else:
            components = []

        ctx.scanned_components = components
        logger.info("source_scan_done", component_count=len(components))
