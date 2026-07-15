"""pytest executor — writes Python test files to a temp dir and runs pytest."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from uuid import UUID

import structlog

from aita.core.executor.test_executor import TestExecutor
from aita.domain.enums import Language
from aita.domain.models import TestCase, TestResult

logger = structlog.get_logger()


class PytestExecutor(TestExecutor):
    def __init__(self, allure_results_dir: Path | None = None) -> None:
        self._allure_dir = allure_results_dir

    async def run(
        self, tests: list[TestCase], base_url: str, run_id: UUID
    ) -> list[TestResult]:
        python_tests = [t for t in tests if t.language == Language.PYTHON]
        if not python_tests:
            return []

        with tempfile.TemporaryDirectory(prefix="aita_pytest_") as tmpdir:
            tmp = Path(tmpdir)

            # Write test files
            for tc in python_tests:
                (tmp / f"{tc.name}.py").write_text(tc.content, encoding="utf-8")

            # Run pytest with JSON report
            report_path = tmp / "report.json"
            cmd = [
                "python", "-m", "pytest", str(tmp),
                "--json-report", f"--json-report-file={report_path}",
                "-v", "--tb=short", "-x",
            ]
            if self._allure_dir:
                cmd += [f"--alluredir={self._allure_dir}"]

            env = {**os.environ, "BASE_URL": base_url}

            logger.info("pytest_run", test_count=len(python_tests), base_url=base_url)
            t0 = time.monotonic()

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            elapsed_ms = int((time.monotonic() - t0) * 1000)

            logger.info("pytest_done", returncode=proc.returncode, elapsed_ms=elapsed_ms)

            return self._parse_report(report_path, run_id, tests)

    def _parse_report(
        self, report_path: Path, run_id: UUID, tests: list[TestCase]
    ) -> list[TestResult]:
        results: list[TestResult] = []
        if not report_path.exists():
            return results

        try:
            data = json.loads(report_path.read_text())
        except Exception:
            return results

        test_map = {tc.name: tc for tc in tests}

        for test in data.get("tests", []):
            name = test.get("nodeid", "").split("::")[-1]
            tc = test_map.get(name)
            outcome = test.get("outcome", "failed")
            results.append(TestResult(
                run_id=run_id,
                test_case_id=tc.id if tc else None,
                status=outcome,
                duration_ms=int(test.get("duration", 0) * 1000),
                error_message=test.get("call", {}).get("longrepr"),
                stdout=test.get("stdout"),
                stderr=test.get("stderr"),
            ))
        return results
