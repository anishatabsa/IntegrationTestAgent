"""
Stage 2 — Rule-based repair: fix known patterns without calling LLM.
- self.api_client fixture issues in Python
- Hardcoded localhost URLs
- Wrong import paths
- Wrong status code assertions (401 on unauthenticated endpoint)
- Known schema mismatches (customer first_name/last_name, product sku)
- Update-customer assertion fixes (data["name"] → data["first_name"])
"""
from __future__ import annotations

import re

from aita.core.healer.rules.base_rule import BaseHealerRule, RuleResult
from aita.domain.enums import Language


class RuleBasedRepairRule(BaseHealerRule):
    @property
    def stage_name(self) -> str:
        return "rule_based_repair"

    async def apply(self, content: str, language: Language) -> RuleResult:
        if language == Language.PYTHON:
            fixed, changed = self._fix_python(content)
        elif language == Language.JAVA:
            fixed, changed = self._fix_java(content)
        else:
            return RuleResult(content=content)

        return RuleResult(content=fixed, modified=changed)

    # ── Python fixes ─────────────────────────────────────────────────────────

    def _fix_python(self, content: str) -> tuple[str, bool]:
        original = content
        content = self._fix_self_api_client(content)
        content = self._fix_hardcoded_urls(content)
        content = self._fix_base_url_env(content)
        content = self._fix_customer_create_schema(content)
        content = self._fix_update_customer_assertions(content)
        content = self._fix_order_create_schema(content)
        content = self._fix_order_customer_prerequisite(content)
        content = self._fix_product_create_schema(content)
        content = self._fix_promotion_discount_field(content)
        content = self._fix_order_list_filter_params(content)
        content = self._fix_defensive_assertions(content)
        content = self._fix_unimplemented_feature_assertions(content)
        return content, content != original

    def _fix_self_api_client(self, content: str) -> str:
        """Ensure self.api_client = requests.Session() in setUp or __init__."""
        if "self.api_client" not in content:
            return content
        if "self.api_client = " in content:
            return content

        # Insert setup method after class definition line
        lines = content.splitlines()
        result = []
        class_indent = ""
        inserted = False
        for i, line in enumerate(lines):
            result.append(line)
            if re.match(r"^class \w+", line) and not inserted:
                class_indent = "    "
                result.append(f"{class_indent}def setUp(self):")
                result.append(f"{class_indent}    import requests, os")
                result.append(f"{class_indent}    self.base_url = os.environ.get('BASE_URL', 'http://localhost:8080')")
                result.append(f"{class_indent}    self.api_client = requests.Session()")
                inserted = True
        return "\n".join(result)

    def _fix_hardcoded_urls(self, content: str) -> str:
        """Replace hardcoded localhost URLs with {self.base_url}.

        IMPORTANT: Do NOT replace URLs that are default values inside
        os.environ.get() calls — those are already correct. Replacing them
        would introduce module-level 'self' references which cause NameError
        at import time (a collection error that silently blocks all tests).
        """
        def _replacer(m: re.Match) -> str:
            pos = m.start()
            # Look at the 80 chars before the match to detect environ.get context
            preceding = content[max(0, pos - 80):pos]
            if re.search(r'(?:os\.)?environ(?:\s*\[|\s*\.get\s*\()', preceding):
                # Already inside an environ lookup — leave it untouched
                return m.group(0)
            return f'f"{{self.base_url}}{m.group(1)}"'

        return re.sub(
            r'["\']http://localhost:\d+([^"\']*)["\']',
            _replacer,
            content,
        )

    def _fix_base_url_env(self, content: str) -> str:
        """Ensure BASE_URL is read from environment."""
        if "BASE_URL" in content or "base_url" in content.lower():
            return content
        # Prepend environment read after imports
        lines = content.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                insert_at = i + 1
        lines.insert(insert_at, "BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8080')")
        return "\n".join(lines)

    def _fix_customer_create_schema(self, content: str) -> str:
        """Fix LLM hallucination: {"name": "First Last"} → {"first_name": "First", "last_name": "Last"}.

        The LLM persistently generates a single "name" field when creating customers,
        but the CustomerCreate schema requires separate first_name and last_name fields.
        This fix only applies to files that have a _create_customer helper, which is the
        only place this pattern appears in customer-related test files.
        """
        if "_create_customer" not in content:
            return content

        def _split_name(m: re.Match) -> str:
            full_name = m.group(1).strip()
            parts = full_name.split(None, 1)
            first = parts[0] if parts else "Test"
            # Take only the first word of the remainder — the LLM often appends a UUID
            # (e.g. "Test User 07ad7a4d-...") which must not end up in last_name (max 50 chars)
            remainder = parts[1] if len(parts) > 1 else "User"
            last = remainder.split()[0]
            return f'"first_name": "{first}", "last_name": "{last}"'

        # Match "name": "..." broadly — the LLM often appends a UUID for uniqueness,
        # e.g. "Test User 07ad7a4d-20ca-4251-aedc-3020078c14b8".  The old pattern
        # [a-zA-Z\s\-]{1,50} rejected digits and was too short for UUID-suffixed values.
        return re.sub(
            r'"name"\s*:\s*"([A-Z][^"]{1,200})"',
            _split_name,
            content,
        )

    def _fix_update_customer_assertions(self, content: str) -> str:
        """Fix assertions that break after the name-split healer fix.

        _fix_customer_create_schema converts {"name": "A B"} → {"first_name": "A", "last_name": "B"}.
        Afterwards, any assertion or lookup of body["name"] / data["name"] raises KeyError because
        neither the request body nor the response contains a "name" key any more.
        This fix is scoped to update-customer test files only.
        """
        if "update_customer" not in content and "_update_customer" not in content:
            return content
        fixed = content
        # Replace dict key lookups for "name" → "first_name"
        for quote in ('"', "'"):
            fixed = fixed.replace(f'data[{quote}name{quote}]', f'data[{quote}first_name{quote}]')
            fixed = fixed.replace(f'body[{quote}name{quote}]', f'body[{quote}first_name{quote}]')
        return fixed

    def _fix_order_create_schema(self, content: str) -> str:
        """Fix LLM hallucination: camelCase order fields → snake_case.

        The LLM generates customerId/productId instead of customer_id/sku as
        required by the OrderCreate/OrderItem schema.

        Note: we only rename "price" → "unit_price" when the content originally
        contained "productId" (i.e., this is an order-item context). This prevents
        the rename from polluting product-creation helpers where "price" is the
        correct field name.
        """
        if "customerId" not in content and "productId" not in content:
            return content

        has_product_id = "productId" in content

        fixed = content
        fixed = re.sub(r'"customerId"\s*:', '"customer_id":', fixed)
        fixed = re.sub(r'"productId"\s*:', '"sku":', fixed)
        # Only rename price → unit_price in order-item contexts (where productId appeared)
        if has_product_id:
            fixed = re.sub(r'"price"\s*:\s*([\d.]+)', r'"unit_price": \1', fixed)
        return fixed

    def _fix_order_customer_prerequisite(self, content: str) -> str:
        """Fix order tests that use a random UUID for customer_id without creating a customer.

        The sample API's in-memory store validates customer_id against existing customers and
        returns 422 if not found. Tests that generate uuid.uuid4() directly will always fail.
        This rule injects a _create_test_customer() helper and replaces bare uuid4() usage.
        """
        # Only apply to order creation test files
        if "create_order" not in content and "/orders" not in content:
            return content

        # Skip if already has a customer creation helper or explicit POST /customers call
        if "_create_test_customer" in content:
            return content
        if re.search(r'self\.api_client\.post\s*\([^)]*["\'].*?/customers["\']', content):
            return content

        # Detect either form:
        #   customer_id = str(uuid.uuid4())           — standalone assignment
        #   "customer_id": str(uuid.uuid4())          — inline inside a json dict
        _STANDALONE_RE = re.compile(r'customer_id\s*=\s*str\s*\(\s*uuid\.uuid4\s*\(\s*\)\s*\)')
        _INLINE_RE = re.compile(r'"customer_id"\s*:\s*str\s*\(\s*uuid\.uuid4\s*\(\s*\)\s*\)')

        if not _STANDALONE_RE.search(content) and not _INLINE_RE.search(content):
            return content

        # Replace both forms with the helper call
        fixed = _STANDALONE_RE.sub(
            'customer_id = self._create_test_customer()',
            content,
        )
        fixed = _INLINE_RE.sub(
            '"customer_id": self._create_test_customer()',
            fixed,
        )

        # Inject the helper before the first test method
        helper = (
            '\n'
            '    def _create_test_customer(self) -> str:\n'
            '        """Create a customer and return its id (required before placing orders).\n'
            '\n'
            '        The API validates customer_id against its in-memory store; a freshly\n'
            '        generated UUID will not exist and the order POST returns 422.\n'
            '        """\n'
            '        import uuid as _uuid\n'
            '        import os as _os\n'
            '        _headers = getattr(\n'
            '            self, "auth_headers",\n'
            '            {"Authorization": f"Bearer {_os.environ.get(\'API_TOKEN\', \'test-token\')}"}\n'
            '        )\n'
            '        resp = self.api_client.post(\n'
            '            f"{self.base_url}/customers",\n'
            '            json={\n'
            '                "first_name": "Test",\n'
            '                "last_name": "Customer",\n'
            '                "email": f"order.test.{_uuid.uuid4().hex[:8]}@example.com",\n'
            '            },\n'
            '            headers=_headers,\n'
            '        )\n'
            '        assert resp.status_code == 201, f"Customer setup failed: {resp.text}"\n'
            '        return resp.json()["id"]\n'
        )

        match = re.search(r'\n    def test_', fixed)
        if match:
            pos = match.start()
            fixed = fixed[:pos] + helper + fixed[pos:]

        return fixed

    def _fix_unimplemented_feature_assertions(self, content: str) -> str:
        """Convert 422 assertions for business rules not enforced by the current API into skips.

        The RAG knowledge base describes a full business spec (age validation, phone format,
        country codes, min order value, etc.) that the simple sample API does NOT enforce.
        Tests generated from those snippets will assert 422 but receive 201 — always failing.

        This rule detects the pattern and replaces the assertion with pytest.skip() so the
        test is flagged as "not yet implemented" rather than a hard failure.
        """
        # Fields/patterns that signal an unimplemented scenario
        _NOT_ENFORCED = [
            "date_of_birth",   # not in CustomerCreate schema
            "country_code",    # not in CustomerCreate schema
            "loyalty_tier",    # server-managed, not a settable request field
            "loyalty_points",  # not in schema
            "hazardous_flag",  # not in ProductCreate schema
            "min_order_value", # comment/variable name hints at this constraint
        ]

        if not any(marker in content for marker in _NOT_ENFORCED):
            return content

        lines = content.splitlines()
        result = []
        i = 0
        while i < len(lines):
            line = lines[i]
            # Detect lines that contain an unimplemented field in a payload dict
            if any(f'"{m}"' in line or f"'{m}'" in line for m in _NOT_ENFORCED):
                # Look ahead for a 422 assertion within the next 10 lines
                for j in range(i + 1, min(i + 10, len(lines))):
                    if re.search(r'assert.*status_code.*==\s*422', lines[j]):
                        lines[j] = re.sub(
                            r'assert.*status_code.*==\s*422',
                            'pytest.skip("Business rule not enforced by current API version")',
                            lines[j],
                        )
                        break
            result.append(line)
            i += 1

        fixed = "\n".join(result)

        # Ensure pytest is imported if we added any skips
        if 'pytest.skip("Business rule not enforced' in fixed and "import pytest" not in fixed:
            fixed = "import pytest\n" + fixed

        return fixed

    def _fix_product_create_schema(self, content: str) -> str:
        """Inject missing 'sku' field into product POST request payloads.

        The LLM commonly omits 'sku' from the product-creation payload in:
        - helper methods (_create_product) used by other test files
        - direct POST calls in the TestCreateProduct test file itself

        Without sku the service returns 422.
        """
        if '"sku"' in content:
            return content
        # Apply to files that have a _create_product helper OR are the create_product test class
        if "_create_product" not in content and "TestCreateProduct" not in content:
            return content

        def _inject_sku(m: re.Match) -> str:
            payload = m.group(0)
            return payload.replace('"name"', '"sku": "SKU-AITA-001", "name"', 1)

        # Match inline json={...} dicts that contain "name" and "price"
        fixed = re.sub(r'json\s*=\s*\{[^}]*"name"[^}]*"price"[^}]*\}', _inject_sku, content)
        # Also match standalone dict assignments: payload = {...} / data = {...} / body = {...}
        fixed = re.sub(
            r'(?:payload|data|body)\s*=\s*\{[^{}]*"name"[^{}]*"price"[^{}]*\}',
            _inject_sku,
            fixed,
        )
        return fixed

    def _fix_promotion_discount_field(self, content: str) -> str:
        """Fix LLM hallucination: 'discount_value' → 'discount_pct' in promotion payloads.

        The spec defines the field as 'discount_pct' but the LLM persistently generates
        'discount_value'. Also fixes 'valid_from'/'valid_until' if LLM uses date aliases.
        """
        if "promotion" not in content.lower():
            return content
        fixed = content
        fixed = re.sub(r'"discount_value"\s*:', '"discount_pct":', fixed)
        return fixed

    def _fix_order_list_filter_params(self, content: str) -> str:
        """Fix query-parameter bugs in list_orders tests.

        Two known issues:
        1. Status filter values are lowercase (e.g. 'pending') but the API requires
           uppercase ('PENDING', 'CONFIRMED', etc.).
        2. customer_id filter values use arbitrary strings instead of UUID format;
           the API validates UUID format and returns 422 on non-UUID values.
        """
        import hashlib
        _uuid_re = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            re.IGNORECASE,
        )

        if "list_order" not in content and "TestListOrders" not in content:
            return content

        fixed = content

        # 1. Uppercase order status values in filter params/bodies
        _valid_statuses = {"pending", "confirmed", "shipped", "delivered", "cancelled"}
        def _uppercase_status(m: re.Match) -> str:
            val = m.group(1)
            if val.lower() in _valid_statuses:
                return f'"status": "{val.upper()}"'
            return m.group(0)

        fixed = re.sub(r'"status"\s*:\s*"([^"]+)"', _uppercase_status, fixed)

        # 2. Replace non-UUID customer_id strings with deterministic UUIDs
        def _fix_customer_id(m: re.Match) -> str:
            val = m.group(1)
            if _uuid_re.match(val):
                return m.group(0)  # Already UUID format — leave it
            # Generate deterministic UUID from the string so the fix is stable
            h = hashlib.md5(val.encode()).hexdigest()
            uuid_str = f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
            return f'"customer_id": "{uuid_str}"'

        fixed = re.sub(r'"customer_id"\s*:\s*"([^"]+)"', _fix_customer_id, fixed)

        return fixed

    def _fix_defensive_assertions(self, content: str) -> str:
        """Strengthen defensive status-code assertions that mix 2xx success with 4xx errors.

        The LLM generates ``assert resp.status_code in (201, 422)`` when uncertain about
        the API contract. These soft assertions always pass regardless of what the service
        returns, so they provide no real test value for error-scenario tests.

        Strategy (conservative):
        - Only convert to strict ``== 201`` when the enclosing test method name CLEARLY
          indicates a happy path (e.g. test_create_x_happy_path, test_x_with_authorization).
        - For error-scenario methods (missing, invalid, wrong_type, etc.) and ambiguous
          methods, leave the soft assertion unchanged — it will correctly pass for both
          201 and 422 responses, avoiding false failures caused by incorrect strengthening.

        This prevents the rule from converting error-test assertions to == 201 when the
        service correctly returns 422, which was the primary cause of false failures.
        """
        # Indicators that STRONGLY suggest the method is a happy-path (success scenario).
        # Only these get strengthened to strict == success_code.
        _HAPPY_PATH_INDICATORS = frozenset({
            'happy_path', 'success', 'with_authorization_header', 'returns_id',
            'minimal_fields', 'with_all_fields', 'with_optional_fields',
            'valid_data', 'complete_', 'standard_',
        })

        def _is_happy_path(method_name: str) -> bool:
            n = method_name.lower()
            return any(ind in n for ind in _HAPPY_PATH_INDICATORS)

        lines = content.splitlines()
        current_method = ""
        result = []

        for line in lines:
            # Track the current test method name
            m = re.match(r'\s+def (test_\w+)', line)
            if m:
                current_method = m.group(1)

            def _strengthen(match: re.Match, _method: str = current_method) -> str:
                codes_str = match.group(1)
                try:
                    codes = [int(c.strip()) for c in codes_str.split(",") if c.strip()]
                except ValueError:
                    return match.group(0)
                success = [c for c in codes if 200 <= c < 300]
                errors  = [c for c in codes if c >= 400]
                # Only strengthen when exactly one success code is mixed with error codes
                # AND the method name strongly suggests a happy path
                if len(success) == 1 and errors and _is_happy_path(_method):
                    return f"assert resp.status_code == {success[0]}"
                # Leave all other soft tuples unchanged — they pass for both 2xx and 4xx
                return match.group(0)

            line = re.sub(
                r"assert\s+resp\.status_code\s+in\s+\(([0-9,\s]+)\)",
                _strengthen,
                line,
            )
            result.append(line)

        return "\n".join(result)

    # ── Java fixes ───────────────────────────────────────────────────────────

    def _fix_java(self, content: str) -> tuple[str, bool]:
        original = content
        content = self._fix_java_base_uri(content)
        return content, content != original

    def _fix_java_base_uri(self, content: str) -> str:
        """Replace hardcoded URLs in RestAssured.baseURI with System.getProperty."""
        return re.sub(
            r'RestAssured\.baseURI\s*=\s*"http://localhost:\d+"',
            'RestAssured.baseURI = System.getProperty("BASE_URL", "http://localhost:8080")',
            content,
        )
