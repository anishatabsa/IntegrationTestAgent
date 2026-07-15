"""
Test generator — calls LLM (with caching) to produce test code per endpoint.
Minimises token usage by skipping unchanged endpoints and using cached responses.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import structlog

from aita.core.generator.prompt_builder import _system_prompt, build_prompt
from aita.domain.enums import Language, TestStatus
from aita.domain.models import (
    EndpointFingerprint,
    EndpointSpec,
    RAGContext,
    ScannedComponent,
    TestCase,
)
from aita.ports.outbound.llm_port import LLMPort

logger = structlog.get_logger()


class TestGenerator:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def generate(
        self,
        endpoint: EndpointSpec,
        scanned: ScannedComponent | None,
        fingerprint: EndpointFingerprint | None,
        rag_context: RAGContext | None,
        language: Language | str,
        ignore_cache: bool = False,
    ) -> tuple[TestCase, int]:
        """
        Returns (TestCase, tokens_used).
        Uses LLM response cache unless ignore_cache=True.
        """
        lang = Language(language) if isinstance(language, str) else language
        system = _system_prompt(lang)
        prompt = build_prompt(
            endpoint=endpoint,
            language=lang,
            scanned=scanned,
            fingerprint=fingerprint,
            rag_context=rag_context,
        )

        tokens = self._llm.count_tokens(prompt)

        if ignore_cache:
            content = await self._llm.complete(prompt, system=system)
            cache_hit = False
        else:
            content, cache_hit = await self._llm.complete_cached(prompt, system=system)

        tokens += self._llm.count_tokens(content) if not cache_hit else 0

        logger.info(
            "test_generated",
            operation_id=endpoint.operation_id,
            cache_hit=cache_hit,
            tokens=tokens,
        )

        test_case = TestCase(
            endpoint_id=uuid.uuid4(),  # will be resolved to real UUID by persist step
            name=f"test_{endpoint.operation_id}",
            content=content,
            language=lang,
            status=TestStatus.GENERATED,
            fingerprint_at_generation=fingerprint.combined_hash if fingerprint else None,
        )
        return test_case, tokens
