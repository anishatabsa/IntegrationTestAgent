"""Unit tests for EndpointFingerprinter."""
import pytest

from aita.core.fingerprint.fingerprinter import EndpointFingerprinter
from aita.domain.models import EndpointSpec


@pytest.fixture
def ep():
    return EndpointSpec(
        operation_id="getProduct",
        method="GET",
        path="/products/{id}",
        summary="Get a product by ID",
        parameters=[{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
        responses={"200": {"description": "OK"}, "404": {"description": "Not Found"}},
    )


def test_fingerprint_is_deterministic(ep):
    fp = EndpointFingerprinter()
    f1 = fp.compute(ep)
    f2 = fp.compute(ep)
    assert f1.combined_hash == f2.combined_hash


def test_fingerprint_changes_on_method_change(ep):
    fp = EndpointFingerprinter()
    f1 = fp.compute(ep)
    ep.method = "POST"
    f2 = fp.compute(ep)
    assert f1.combined_hash != f2.combined_hash
    assert f1.path_hash != f2.path_hash


def test_fingerprint_changes_on_schema_change(ep):
    fp = EndpointFingerprinter()
    f1 = fp.compute(ep)
    ep.responses["500"] = {"description": "Server Error"}
    f2 = fp.compute(ep)
    assert f1.schema_hash != f2.schema_hash
    assert f1.combined_hash != f2.combined_hash


def test_fingerprint_has_8_char_hashes(ep):
    fp = EndpointFingerprinter()
    f = fp.compute(ep)
    assert len(f.path_hash) == 8
    assert len(f.schema_hash) == 8
    assert len(f.security_hash) == 8
    assert len(f.source_hash) == 8
    assert len(f.combined_hash) == 8
