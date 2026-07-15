"""Maven executor — writes Java test files and runs mvn test."""
from __future__ import annotations

import asyncio
import os
import re
import tempfile
from pathlib import Path
from uuid import UUID

import structlog

from aita.core.executor.test_executor import TestExecutor
from aita.domain.enums import Language
from aita.domain.models import TestCase, TestResult

logger = structlog.get_logger()

_MAVEN_POM = """\
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>aita</groupId>
  <artifactId>generated-tests</artifactId>
  <version>1.0</version>
  <dependencies>
    <dependency>
      <groupId>io.rest-assured</groupId>
      <artifactId>rest-assured</artifactId>
      <version>5.4.0</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.2</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
      </plugin>
    </plugins>
  </build>
</project>
"""


class MavenExecutor(TestExecutor):
    async def run(
        self, tests: list[TestCase], base_url: str, run_id: UUID
    ) -> list[TestResult]:
        java_tests = [t for t in tests if t.language == Language.JAVA]
        if not java_tests:
            return []

        with tempfile.TemporaryDirectory(prefix="aita_mvn_") as tmpdir:
            tmp = Path(tmpdir)
            test_src = tmp / "src" / "test" / "java" / "aita"
            test_src.mkdir(parents=True)

            (tmp / "pom.xml").write_text(_MAVEN_POM)

            for tc in java_tests:
                class_match = re.search(r"public\s+class\s+(\w+)", tc.content)
                fname = (class_match.group(1) + ".java") if class_match else f"{tc.name}.java"
                (test_src / fname).write_text(tc.content, encoding="utf-8")

            cmd = ["mvn", "test", "-q", f"-DBASE_URL={base_url}"]
            env = {**os.environ, "BASE_URL": base_url}

            logger.info("mvn_run", test_count=len(java_tests))
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(tmp),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            return self._parse_surefire(tmp / "target" / "surefire-reports", run_id, java_tests)

    def _parse_surefire(
        self, reports_dir: Path, run_id: UUID, tests: list[TestCase]
    ) -> list[TestResult]:
        results: list[TestResult] = []
        if not reports_dir.exists():
            return results

        import xml.etree.ElementTree as ET

        for xml_file in reports_dir.glob("TEST-*.xml"):
            try:
                tree = ET.parse(xml_file)
                root = tree.getroot()
                for tc_el in root.findall("testcase"):
                    name = tc_el.get("name", "")
                    failure = tc_el.find("failure")
                    error = tc_el.find("error")
                    duration_ms = int(float(tc_el.get("time", 0)) * 1000)
                    status = "passed"
                    err_msg = None
                    if failure is not None:
                        status = "failed"
                        err_msg = failure.get("message") or failure.text
                    elif error is not None:
                        status = "error"
                        err_msg = error.get("message") or error.text

                    results.append(TestResult(
                        run_id=run_id,
                        status=status,
                        duration_ms=duration_ms,
                        error_message=err_msg,
                    ))
            except Exception as exc:
                logger.warning("surefire_parse_error", file=str(xml_file), error=str(exc))

        return results
