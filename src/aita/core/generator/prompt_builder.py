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

SCHEMA FIDELITY (critical):
- Request body field names MUST exactly match the "Request Body" schema in the endpoint spec.
- NEVER invent or rename fields based on the knowledge base snippets.
  The knowledge base describes BUSINESS SCENARIOS to test — not API schemas.
  Use snippet content only to determine WHAT scenarios to cover; always use spec field names in payloads.
- If a business rule mentions a field (e.g. "date_of_birth") that is NOT in the spec,
  skip tests that require sending that field — the API does not support it yet.

REQUIRED FIELD COMPLETENESS (critical):
- Every happy-path test MUST include ALL required fields from the spec schema.
  Example: if the spec marks both "name" AND "sku" as required for POST /products,
  every successful creation test must send both — omitting a required field turns
  a happy-path test into a validation-error test.
- Before writing each happy-path payload, check the spec's "required" list and
  confirm every item is present in the payload.

ASSERTION ACCURACY:
- Happy-path test methods MUST use strict equality: assert resp.status_code == 201
  NEVER write assert resp.status_code in (201, 422) — mixing a success code with
  an error code is a non-assertion that passes even when the request is rejected.
  The only acceptable tuple assertions are all-success (200, 201) or all-error (400, 422).
- When a schema has a convenience "name" field that the service splits into
  "first_name" / "last_name", assert against "first_name" and "last_name"
  separately — never assert first_name == "First Last" (the combined value).
- When testing path parameters with special/non-ASCII characters, include 405
  (Method Not Allowed) alongside 400/404/422 as acceptable error codes, since
  special characters can resolve to a different route.

KNOWLEDGE BASE USAGE (when snippets are provided):
- Extract testable business invariants: constraints, limits, forbidden states, valid enumerations.
- Each extracted invariant should become at least one test method.
- Use only spec-defined fields to exercise these invariants.
- If the invariant cannot be tested with the current spec fields, add a pytest.skip() with a note.

IMPROVEMENT MODE (when ## Existing Tests is present):
- You are IMPROVING an existing test suite, not generating from scratch.
- Output the COMPLETE test file — include ALL existing methods plus any fixes or additions.
- For each existing method: copy it unchanged if correct, or rewrite it if it has a bug.
- Add new methods at the END of the class for scenarios not yet covered.
- Do NOT omit any existing method — every method you omit will be lost.
- Your output is a COMPLETE replacement of the existing file, not a partial patch.
- CRITICAL: The spec's field names ALWAYS win over the existing test. If the existing test
  uses "discount_value" but the spec shows "discount_pct", you MUST fix it to "discount_pct".
  Re-read the spec's Request Body schema before deciding whether an existing method is correct.

API CONTRACT RULES (apply even when improving existing tests):
- ID-type query parameters (customer_id, product_id, order_id) must be UUID format.
  Use str(uuid.uuid4()) to generate valid test UUIDs — never use strings like 'cust-123'.
- Status enum values are case-sensitive — use the exact case shown in the spec's enum list
  (e.g. "PENDING" not "pending", "CONFIRMED" not "confirmed").
- Filter query parameters that accept invalid values will return 422 — do not assert 200
  for tests that pass values outside the spec's defined format or enum.

CROSS-ENDPOINT DEPENDENCIES (critical for order tests):
- POST /orders requires `customer_id` to reference an ALREADY-EXISTING customer.
  The service validates customer_id against its in-memory store and returns 422 if the
  customer does not exist. A freshly generated uuid.uuid4() will NEVER be found.
  Every order-creation test MUST first call POST /customers and use the `id` from the
  response as customer_id. Add a _create_test_customer() helper and call it in setUp
  or at the start of each test that creates an order.
- Similarly, if an OrderItem references a product by product_id, create the product first
  via POST /products and use its returned id.

KNOWLEDGE BASE CAVEATS (critical — prevents false test failures):
- The knowledge base describes the FULL business specification for this domain.
  Many rules in it are NOT YET ENFORCED by this particular API version.
- A constraint is testable ONLY if it is explicitly enforced by the API schema/implementation:
  e.g. a Pydantic field with a validator, a min/max constraint, or an explicit HTTPException.
- For each 422-asserting test scenario from the knowledge base, ask: "Does the Request Body
  schema in the spec show a validator for this constraint?" If not, use pytest.skip() instead.
- Specific fields/rules that are NOT enforced by the current API version:
  - date_of_birth, minimum age validation — not in any request schema
  - country_code / postcode format validation — not in CustomerCreate
  - loyalty_tier / loyalty_points — server-managed, not a request field
  - min_order_value (10.00) — not enforced; the API only rejects total > 50,000
  - max_items_per_order (50) — not enforced
  - Order status lifecycle / transition rules — not enforced at creation time
  - SKU format patterns (ELEC-, CLOTH-, HZ-) — only min_length=3 is enforced
  - phone format (E.164) — accepted as any string, not validated
  - Product status (ACTIVE/INACTIVE/DISCONTINUED) — managed by server on creation

TYPE COERCION AND FIELD CONSTRAINTS (critical — prevents false 422 assertions):
- email field in CustomerCreate IS format-validated with a regex (name@domain.tld).
  Invalid formats (missing @, no TLD, spaces) → 422. DO assert 422 for "notanemail".
- stock field in ProductCreate has ge=0 AND le=100000. Negative stock → 422.
  Stock > 100000 → 422. Stock = 0 is valid → 201.
- first_name/last_name in CustomerCreate: max_length=50 enforced. NO min_length.
  Sending a 1-character first_name is accepted → 201.
  Sending 51+ character first_name → 422.
- product `name` field has min_length=1 AND max_length=200.
  Empty string name → 422. Name > 200 chars → 422.
- product `sku` field has min_length=3 AND max_length=50. SKU < 3 chars → 422.
- Pydantic v2 coerces integers to strings for `str` fields: sending `name: 123` results
  in `name: "123"` which is valid → 201. Do NOT assert 422 for int values in str fields.
- Similarly, floats are coerced to ints for `int` fields (1.5 → 1), not rejected.
- null/None for a non-Optional `int` or `str` field DOES produce a 422 validation error.
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

SCHEMA FIDELITY (critical):
- Request body field names MUST exactly match the "Request Body" schema in the endpoint spec.
- NEVER invent or rename fields based on the knowledge base snippets.
  Use snippet content only to determine WHAT scenarios to cover; always use spec field names in payloads.
- If a business rule references a field not in the spec, skip that test with a comment.

KNOWLEDGE BASE USAGE (when snippets are provided):
- Extract testable business invariants and generate at least one test per invariant.
- Use only spec-defined fields to exercise these invariants.
"""


def _system_prompt(language: Language) -> str:
    return _SYSTEM_JAVA if language == Language.JAVA else _SYSTEM_PYTHON


def build_prompt(
    endpoint: EndpointSpec,
    language: Language,
    scanned: ScannedComponent | None = None,
    fingerprint: EndpointFingerprint | None = None,
    rag_context: RAGContext | None = None,
    existing_content: str | None = None,
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
            parts.append(
                "\n## Relevant Knowledge Base Snippets\n"
                "(Use these business rules to generate ADDITIONAL test methods beyond the basic "
                "CRUD happy-path. Cover every constraint, validation rule, and domain invariant "
                "mentioned below.)"
            )
            for snippet in rag_context.knowledge_snippets[:5]:
                parts.append(f"\n---\n{snippet}")

    # Existing test file — injected when FetchExistingTestsStep found a prior version
    if existing_content:
        parts.append(
            "\n## Existing Tests (Review and Improve)\n"
            "The following test file already exists for this endpoint on the automation branch.\n"
            "Output a COMPLETE, IMPROVED version of this file:\n"
            "- Include ALL existing test methods. Copy them unchanged if already correct.\n"
            "- Fix methods that have bugs (wrong assertion, missing required field, bad payload).\n"
            "- Add new test methods at the END of the class for uncovered scenarios.\n"
            "- Preserve imports, setUp, and helper methods from the existing file.\n"
            "- Do NOT omit any existing test method — your output fully replaces this file.\n"
        )
        parts.append(f"```python\n{existing_content.strip()}\n```")

    parts.append(f"\n## Task\nGenerate integration tests in {language.value.upper()}.")
    return "\n".join(parts)
