"""OpenAPI 3.x spec parser."""
from __future__ import annotations

from pathlib import Path

import yaml

from aita.core.spec.parser import BaseSpecParser
from aita.domain.enums import SpecFormat
from aita.domain.exceptions import SpecParseError
from aita.domain.models import EndpointSpec


class OpenAPIParser(BaseSpecParser):
    @property
    def spec_format(self) -> SpecFormat:
        return SpecFormat.OPENAPI_3

    async def parse(self, repo_dir: Path) -> list[EndpointSpec]:
        spec_file = self._find_spec_file(repo_dir)
        try:
            raw = yaml.safe_load(spec_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SpecParseError(f"Failed to parse {spec_file}: {exc}") from exc

        endpoints: list[EndpointSpec] = []
        paths = raw.get("paths", {})

        for path, path_item in paths.items():
            for method, operation in path_item.items():
                if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    continue
                if not isinstance(operation, dict):
                    continue

                op_id = operation.get("operationId") or f"{method.upper()}_{path.replace('/', '_').strip('_')}"
                endpoints.append(EndpointSpec(
                    operation_id=op_id,
                    method=method.upper(),
                    path=path,
                    summary=operation.get("summary", ""),
                    parameters=operation.get("parameters", []),
                    request_body=operation.get("requestBody"),
                    responses=operation.get("responses", {}),
                    security=operation.get("security", []),
                    tags=operation.get("tags", []),
                    raw=operation,
                ))

        return endpoints
