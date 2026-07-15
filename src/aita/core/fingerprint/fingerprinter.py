"""
Semantic endpoint fingerprinter.
Computes separate hashes for: path, schema, security, source scan.
Combined hash is XOR of all four — change in any dimension triggers regen.
"""
from __future__ import annotations

import hashlib
import json

import xxhash

from aita.domain.models import EndpointFingerprint, EndpointSpec, ScannedComponent


def _sha8(data: str) -> str:
    """8-char hex hash for a single dimension."""
    return xxhash.xxh64(data.encode()).hexdigest()[:8]


def _stable_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


class EndpointFingerprinter:
    def compute(
        self,
        ep: EndpointSpec,
        scanned: ScannedComponent | None = None,
    ) -> EndpointFingerprint:
        # Dimension 1: path + method
        path_hash = _sha8(f"{ep.method}:{ep.path}")

        # Dimension 2: request/response schema
        schema_data = {
            "parameters": ep.parameters,
            "requestBody": ep.request_body,
            "responses": ep.responses,
        }
        schema_hash = _sha8(_stable_json(schema_data))

        # Dimension 3: security requirements
        security_hash = _sha8(_stable_json(ep.security))

        # Dimension 4: source scan (auth annotations, validation annotations)
        source_data = {
            "auth": sorted(scanned.auth_annotations) if scanned else [],
            "validation": sorted(scanned.validation_annotations) if scanned else [],
            "url_pattern": scanned.url_pattern if scanned else "",
        }
        source_hash = _sha8(_stable_json(source_data))

        # Combined: concatenate all four and hash again
        combined = _sha8(path_hash + schema_hash + security_hash + source_hash)

        return EndpointFingerprint(
            operation_id=ep.operation_id,
            combined_hash=combined,
            path_hash=path_hash,
            schema_hash=schema_hash,
            security_hash=security_hash,
            source_hash=source_hash,
        )
