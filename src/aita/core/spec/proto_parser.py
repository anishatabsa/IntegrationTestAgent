"""gRPC / protobuf spec parser."""
from __future__ import annotations

import re
from pathlib import Path

from aita.core.spec.parser import BaseSpecParser
from aita.domain.enums import SpecFormat
from aita.domain.exceptions import SpecNotFoundError, SpecParseError
from aita.domain.models import EndpointSpec

_RPC_RE = re.compile(
    r"rpc\s+(\w+)\s*\(\s*(\w+)\s*\)\s+returns\s*\(\s*(\w+)\s*\)", re.MULTILINE
)
_SERVICE_RE = re.compile(r"service\s+(\w+)\s*\{", re.MULTILINE)


class ProtoParser(BaseSpecParser):
    @property
    def spec_format(self) -> SpecFormat:
        return SpecFormat.PROTO

    async def parse(self, repo_dir: Path) -> list[EndpointSpec]:
        proto_files = list(repo_dir.rglob("*.proto"))
        if not proto_files:
            raise SpecNotFoundError(f"No .proto files found in {repo_dir}")

        endpoints: list[EndpointSpec] = []
        for proto_file in proto_files:
            try:
                content = proto_file.read_text(encoding="utf-8")
            except Exception as exc:
                raise SpecParseError(f"Failed to read {proto_file}: {exc}") from exc

            service_match = _SERVICE_RE.search(content)
            service_name = service_match.group(1) if service_match else "Unknown"

            for rpc_match in _RPC_RE.finditer(content):
                rpc_name, req_type, resp_type = rpc_match.groups()
                op_id = f"{service_name}_{rpc_name}"
                endpoints.append(EndpointSpec(
                    operation_id=op_id,
                    method="GRPC",
                    path=f"/{service_name}/{rpc_name}",
                    summary=f"RPC {rpc_name}({req_type}) → {resp_type}",
                    parameters=[],
                    request_body={"type": req_type},
                    responses={"0": {"description": resp_type}},
                    tags=[service_name],
                    raw={"rpc": rpc_name, "request": req_type, "response": resp_type},
                ))

        return endpoints
