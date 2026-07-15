"""Builds LLM prompts for test generation, injecting RAG context and learned patterns."""
from __future__ import annotations

import json

from aita.domain.enums import Language
from aita.domain.models import EndpointFingerprint, EndpointSpec, RAGContext, ScannedComponent


_SYSTEM_PYTHON = """\
You are an expert software engineer specialising in Python integration testing with pytest and requests.
Generate comprehensive, runnable pytest test cases for the given API endpoint.
Rules:
- Use self.api_client (a requests.Session) with base_url from environment variable BASE_URL.
- Each test method must be fully self-contained: create all required data, assert the response.
- Include happy-path, edge cases, and error scenarios.
- Never hardcode base URLs or secrets.
- Do NOT import from the service under test.
- Output ONLY valid Python code, no markdown fences, no explanation.
"""

_SYSTEM_JAVA = """\
You are an expert software engineer specialising in Java integration testing with JUnit 5 and RestAssured.
Generate comprehensive, runnable JUnit 5 test cases for the given API endpoint.
Rules:
- Use RestAssured with baseURI from system property BASE_URL.
- Each test method must be self-contained.
- Include happy-path, edge cases, and error scenarios.
- Never hardcode base URLs or secrets.
- Output ONLY valid Java code, no markdown fences, no explanation.
"""


def _system_prompt(language: Language) -> str:
    return _SYSTEM_JAVA if language == Language.JAVA else _SYSTEM_PYTHON


def build_prompt(
    endpoint: EndpointSpec,
    language: Language,
    scanned: ScannedComponent | None = None,
    fingerprint: EndpointFingerprint | None = None,
    rag_context: RAGContext | None = None,
) -> str:
    parts: list[str] = []

    # Core endpoint spec
    parts.append("## Endpoint Specification")
    parts.append(f"Operation ID : {endpoint.operation_id}")
    parts.append(f"Method       : {endpoint.method}")
    parts.append(f"Path         : {endpoint.path}")
    parts.append(f"Summary      : {endpoint.summary}")
    if endpoint.parameters:
        parts.append(f"Parameters   :\n{json.dumps(endpoint.parameters, indent=2)}")
    if endpoint.request_body:
        parts.append(f"Request Body :\n{json.dumps(endpoint.request_body, indent=2)}")
    if endpoint.responses:
        parts.append(f"Responses    :\n{json.dumps(endpoint.responses, indent=2)}")
    if endpoint.security:
        parts.append(f"Security     :\n{json.dumps(endpoint.security, indent=2)}")

    # Source scan context
    if scanned:
        parts.append("\n## Source Scan Context")
        parts.append(f"Controller   : {scanned.controller_class}.{scanned.method_name}")
        parts.append(f"URL Pattern  : {scanned.url_pattern}")
        if scanned.auth_annotations:
            parts.append(f"Auth         : {', '.join(scanned.auth_annotations)}")
        if scanned.validation_annotations:
            parts.append(f"Validations  : {', '.join(scanned.validation_annotations)}")

    # RAG / learned context
    if rag_context:
        if rag_context.patterns:
            parts.append("\n## Learned Patterns (apply these to avoid past mistakes)")
            for pat in rag_context.patterns[:5]:
                parts.append(f"- [{pat.pattern_type}] {pat.description}")
                if pat.prompt_snippet:
                    parts.append(f"  Hint: {pat.prompt_snippet}")

        if rag_context.feedback_items:
            parts.append("\n## Past Failures to Avoid")
            for fb in rag_context.feedback_items[:5]:
                parts.append(f"- {fb.feedback_type}: {fb.description}")
                if fb.fix_hint:
                    parts.append(f"  Fix: {fb.fix_hint}")

        if rag_context.knowledge_snippets:
            parts.append("\n## Relevant Knowledge Base Snippets")
            for snippet in rag_context.knowledge_snippets[:3]:
                parts.append(snippet)

    parts.append(f"\n## Task\nGenerate integration tests in {language.value.upper()}.")
    return "\n".join(parts)
