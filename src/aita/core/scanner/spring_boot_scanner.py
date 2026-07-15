"""Spring Boot / Java source scanner — detects @RestController endpoints."""
from __future__ import annotations

import re
from pathlib import Path

from aita.core.scanner.source_scanner import BaseSourceScanner
from aita.domain.enums import Language
from aita.domain.models import ScannedComponent

_MAPPING_RE = re.compile(
    r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)"
    r'(?:\s*\(\s*(?:value\s*=\s*)?["\']([^"\']*)["\'])?'
)
_CLASS_RE = re.compile(r"public\s+class\s+(\w+)")
_METHOD_RE = re.compile(r"public\s+\S+\s+(\w+)\s*\(")
_AUTH_RE = re.compile(r"@(PreAuthorize|Secured|RolesAllowed|PermitAll|DenyAll)\s*(?:\([^)]*\))?")
_VALID_RE = re.compile(r"@(Valid|Validated|NotNull|NotBlank|Size|Min|Max)\b")

_HTTP_METHOD_MAP = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
    "RequestMapping": "ANY",
}


class SpringBootScanner(BaseSourceScanner):
    @property
    def language(self) -> Language:
        return Language.JAVA

    async def scan(self, repo_dir: Path) -> list[ScannedComponent]:
        components: list[ScannedComponent] = []

        for java_file in repo_dir.rglob("*.java"):
            content = java_file.read_text(encoding="utf-8", errors="ignore")

            if "@RestController" not in content and "@Controller" not in content:
                continue

            class_match = _CLASS_RE.search(content)
            class_name = class_match.group(1) if class_match else java_file.stem

            auth_anns = _AUTH_RE.findall(content)
            valid_anns = _VALID_RE.findall(content)

            lines = content.splitlines()
            for i, line in enumerate(lines):
                mapping_match = _MAPPING_RE.search(line)
                if not mapping_match:
                    continue

                ann_name = mapping_match.group(1)
                url = mapping_match.group(2) or ""
                http_method = _HTTP_METHOD_MAP.get(ann_name, "ANY")

                # Look ahead for method name
                method_name = "unknown"
                for j in range(i + 1, min(i + 5, len(lines))):
                    m = _METHOD_RE.search(lines[j])
                    if m:
                        method_name = m.group(1)
                        break

                op_id = f"{class_name}_{method_name}"
                components.append(ScannedComponent(
                    operation_id=op_id,
                    controller_class=class_name,
                    method_name=method_name,
                    http_method=http_method,
                    url_pattern=url,
                    auth_annotations=auth_anns,
                    validation_annotations=valid_anns,
                ))

        return components
