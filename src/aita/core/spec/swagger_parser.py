"""Swagger 2.0 spec parser."""
from __future__ import annotations

from pathlib import Path

import yaml

from aita.core.spec.parser import BaseSpecParser
from aita.domain.enums import SpecFormat
from aita.domain.exceptions import SpecParseError
from aita.domain.models import EndpointSpec


class SwaggerParser(BaseSpecParser):
    @property
    def spec_format(self) -> SpecFormat:
        return SpecFormat.SWAGGER_2

    async def parse(self, repo_dir: Path) -> list[EndpointSpec]:
        spec_file = self._find_spec_file(repo_dir)
        try:
            raw = yaml.safe_load(spec_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SpecParseError(f"Failed to parse {spec_file}: {exc}") from exc

        base_path = raw.get("basePath", "")
        endpoints: list[EndpointSpec] = []

        for path, path_item in raw.get("paths", {}).items():
            full_path = base_path + path
            for method, operation in path_item.items():
                if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                    continue
                if not isinstance(operation, dict):
                    continue

                op_id = (
                    operation.get("operationId")
                    or f"{method.upper()}_{path.replace('/', '_').strip('_')}"
                )

                # Convert Swagger 2 responses to OpenAPI-like dict
                responses = {
                    str(code): {"description": r.get("description", "")}
                    for code, r in operation.get("responses", {}).items()
                }

                endpoints.append(EndpointSpec(
                    operation_id=op_id,
                    method=method.upper(),
                    path=full_path,
                    summary=operation.get("summary", ""),
                    parameters=operation.get("parameters", []),
                    request_body=None,  # Swagger 2 uses parameters with in:body
                    responses=responses,
                    security=operation.get("security", []),
                    tags=operation.get("tags", []),
                    raw=operation,
                ))

        return endpoints
