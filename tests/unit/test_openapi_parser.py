"""Unit tests for OpenAPI 3 parser."""
import tempfile
from pathlib import Path

import pytest

from aita.core.spec.openapi_parser import OpenAPIParser

SAMPLE_SPEC = """
openapi: "3.0.3"
info:
  title: Product API
  version: "1.0"
paths:
  /products:
    get:
      operationId: listProducts
      summary: List all products
      responses:
        "200":
          description: OK
    post:
      operationId: createProduct
      summary: Create a product
      requestBody:
        content:
          application/json:
            schema:
              type: object
      responses:
        "201":
          description: Created
  /products/{id}:
    get:
      operationId: getProduct
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: OK
        "404":
          description: Not Found
"""


@pytest.fixture
def spec_dir(tmp_path):
    (tmp_path / "openapi.yaml").write_text(SAMPLE_SPEC)
    return tmp_path


@pytest.mark.asyncio
async def test_parses_all_endpoints(spec_dir):
    parser = OpenAPIParser()
    endpoints = await parser.parse(spec_dir)
    assert len(endpoints) == 3
    op_ids = {ep.operation_id for ep in endpoints}
    assert op_ids == {"listProducts", "createProduct", "getProduct"}


@pytest.mark.asyncio
async def test_endpoint_fields(spec_dir):
    parser = OpenAPIParser()
    endpoints = await parser.parse(spec_dir)
    get_prod = next(ep for ep in endpoints if ep.operation_id == "getProduct")
    assert get_prod.method == "GET"
    assert get_prod.path == "/products/{id}"
    assert len(get_prod.parameters) == 1
    assert "200" in get_prod.responses
    assert "404" in get_prod.responses
