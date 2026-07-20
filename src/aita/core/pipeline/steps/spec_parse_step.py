"""Step 2 — Parse service specification (OpenAPI / Swagger / Proto)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import structlog

from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.core.spec.parser import SpecParserRegistry
from aita.domain.enums import PipelineStep
from aita.domain.exceptions import PipelineStepError, SpecNotFoundError

logger = structlog.get_logger()


class SpecParseStep(BaseStep):
    def __init__(self, parser_registry: SpecParserRegistry) -> None:
        self._registry = parser_registry

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.SPEC_PARSE

    def should_skip(self, ctx: PipelineContext) -> bool:
        # Skip only if there's no repo dir AND no URL to fetch from
        return ctx.repo_dir is None and not ctx.options.spec_url and not ctx.options.base_url

    async def _fetch_spec_from_url(self, url: str, dest_dir: Path) -> None:
        """Fetch OpenAPI JSON from a live service and write openapi.json into dest_dir."""
        import httpx
        logger.info("spec_fetch_url", url=url)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        spec_file = dest_dir / "openapi.json"
        spec_file.write_text(resp.text, encoding="utf-8")
        logger.info("spec_fetched", path=str(spec_file))

    async def _execute(self, ctx: PipelineContext) -> None:
        service = ctx.options.service_name

        # Resolve the spec URL (explicit spec_url or infer from base_url)
        spec_url = ctx.options.spec_url
        if not spec_url and ctx.options.base_url:
            spec_url = ctx.options.base_url.rstrip("/") + "/openapi.json"

        repo_dir = ctx.repo_dir

        # ── GitHub API mode: no local clone, must download spec ───────────────
        # When git_pull was skipped (GitHub URL + live service), ctx.repo_dir is
        # None.  Download the spec into a temp directory so the parser can read it.
        if repo_dir is None and spec_url:
            tmp = Path(tempfile.mkdtemp(prefix="aita_spec_"))
            try:
                await self._fetch_spec_from_url(spec_url, tmp)
            except Exception as exc:
                raise PipelineStepError(
                    self.step_id,
                    f"Failed to fetch spec from '{spec_url}': {exc}",
                    cause=exc,
                ) from exc
            repo_dir = tmp  # parser reads from here; temp dir cleaned by OS on reboot

        # ── Local-clone mode: only fetch if spec file not already in repo ─────
        elif repo_dir is not None and spec_url:
            from aita.domain.exceptions import SpecNotFoundError as _SNF
            try:
                self._registry.detect(repo_dir)
            except _SNF:
                try:
                    await self._fetch_spec_from_url(spec_url, repo_dir)
                except Exception as exc:
                    logger.warning("spec_fetch_failed", url=spec_url, error=str(exc))

        try:
            parser = self._registry.detect(repo_dir)
        except SpecNotFoundError as exc:
            raise PipelineStepError(self.step_id, str(exc), cause=exc) from exc

        logger.info("spec_parse", format=parser.spec_format, service=service)
        endpoints = await parser.parse(repo_dir)

        ctx.endpoints = endpoints
        logger.info("spec_parse_done", endpoint_count=len(endpoints))
