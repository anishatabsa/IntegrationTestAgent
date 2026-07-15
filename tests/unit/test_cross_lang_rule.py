"""Unit tests for CrossLangContaminationRule — the most critical healer stage."""
import pytest

from aita.core.healer.rules.cross_lang_rule import CrossLangContaminationRule
from aita.domain.enums import Language


@pytest.fixture
def rule():
    return CrossLangContaminationRule()


JAVA_WITH_PYTHON = """\
public class TestProduct {
    @Test
    public void testGetProduct() {
        // valid Java
    }

    def test_get_product(self):
        import requests
        resp = self.api_client.get("/products/1")
        assert resp.status_code == 200
}
"""

CLEAN_JAVA = """\
public class TestProduct {
    @Test
    public void testGetProduct() {
        given().when().get("/products/1").then().statusCode(200);
    }
}
"""

PYTHON_WITH_JAVA = """\
import requests

class TestProduct(unittest.TestCase):
    @Test
    public void testGetProduct() {
        // oops
    }

    def test_get(self):
        pass
"""


@pytest.mark.asyncio
async def test_detects_python_in_java(rule):
    result = await rule.apply(JAVA_WITH_PYTHON, Language.JAVA)
    assert result.modified is True
    assert "def test_get_product" not in result.content


@pytest.mark.asyncio
async def test_clean_java_passes_unchanged(rule):
    result = await rule.apply(CLEAN_JAVA, Language.JAVA)
    assert result.modified is False
    assert result.content == CLEAN_JAVA


@pytest.mark.asyncio
async def test_detects_java_in_python(rule):
    result = await rule.apply(PYTHON_WITH_JAVA, Language.PYTHON)
    assert result.modified is True
    assert "@Test" not in result.content
    assert "def test_get" in result.content  # clean Python preserved
