"""Step 4 — Compute endpoint fingerprints and detect changed endpoints."""
from __future__ import annotations

import structlog

from aita.core.fingerprint.fingerprinter import EndpointFingerprinter
from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.domain.enums import PipelineStep
from aita.ports.outbound.cache_port import CachePort

logger = structlog.get_logger()

_FP_KEY = "fingerprint:{service}:{operation_id}"


class EndpointDiffStep(BaseStep):
    def __init__(self, fingerprinter: EndpointFingerprinter, cache: CachePort) -> None:
        self._fp = fingerprinter
        self._cache = cache

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.ENDPOINT_DIFF

    def should_skip(self, ctx: PipelineContext) -> bool:
        return not ctx.endpoints

    async def _execute(self, ctx: PipelineContext) -> None:
        service = ctx.options.service_name
        force = ctx.options.force_generate
        selected = set(ctx.options.selected_operations)

        changed: list[str] = []

        for ep in ctx.endpoints:
            if selected and ep.operation_id not in selected:
                continue

            # Compute current fingerprint
            scanned = next(
                (c for c in ctx.scanned_components if c.operation_id == ep.operation_id), None
            )
            fp = self._fp.compute(ep, scanned)
            ctx.fingerprints[ep.operation_id] = fp

            if force:
                changed.append(ep.operation_id)
                continue

            # Compare with stored fingerprint
            key = _FP_KEY.format(service=service, operation_id=ep.operation_id)
            stored = await self._cache.get(key)
            if stored is None or stored.get("combined_hash") != fp.combined_hash:
                changed.append(ep.operation_id)
                # Store new fingerprint (no TTL — persists until endpoint changes)
                await self._cache.set(key, {"combined_hash": fp.combined_hash,
                                            "path_hash": fp.path_hash,
                                            "schema_hash": fp.schema_hash,
                                            "security_hash": fp.security_hash,
                                            "source_hash": fp.source_hash})

        ctx.changed_operations = changed
        logger.info(
            "endpoint_diff_done",
            total=len(ctx.endpoints),
            changed=len(changed),
            force=force,
        )
