"""pytest executor — writes Python test files to a temp dir and runs pytest."""
from __future__ import annotations

import asyncio
import json
import os
import sys
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

            # Run pytest with JSON report.
            # Key details:
            #   - sys.executable: use the exact Python that is running uvicorn (venv guaranteed)
            #   - cwd=tmp: start pytest from the temp dir so it does NOT pick up
            #     IntegrationTestAgent's pyproject.toml (which has asyncio_mode=auto)
            #   - -p no:asyncio: disable pytest-asyncio for generated (sync) tests
            #   - --override-ini=asyncio_mode=strict: belt-and-suspenders guard
            report_path = tmp / "report.json"
            cmd = [
                sys.executable, "-m", "pytest", str(tmp),
                "--json-report", f"--json-report-file={report_path}",
                "-p", "no:asyncio",
                "--continue-on-collection-errors",  # don't let one bad file block others
                "-v", "--tb=short",
            ]
            if self._allure_dir:
                try:
                    import allure_pytest  # noqa: F401 — only add flag if plugin is installed
                    cmd += [f"--alluredir={self._allure_dir}"]
                except ImportError:
                    logger.warning("allure_pytest_not_installed", skipping_alluredir=True)

            env = {**os.environ, "BASE_URL": base_url}

            logger.info(
                "pytest_run",
                test_count=len(python_tests),
                base_url=base_url,
                python=sys.executable,
                cwd=str(tmp),
            )
            t0 = time.monotonic()

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(tmp),          # isolate from project's pyproject.toml
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            elapsed_ms = int((time.monotonic() - t0) * 1000)

            stdout_str = stdout.decode(errors="replace")
            stderr_str = stderr.decode(errors="replace")

            logger.info("pytest_done", returncode=proc.returncode, elapsed_ms=elapsed_ms)

            # Always dump stdout to a debug file next to the report so it survives
            # the TemporaryDirectory cleanup (we write it to CWD which is tmp itself)
            debug_out = tmp / "pytest_output.txt"
            debug_out.write_text(
                f"returncode: {proc.returncode}\n\nSTDOUT:\n{stdout_str}\n\nSTDERR:\n{stderr_str}",
                encoding="utf-8",
            )
            # Copy to a persistent location users can inspect
            import shutil
            persistent_debug = Path.home() / ".aita_pytest_debug.txt"
            shutil.copy(debug_out, persistent_debug)
            logger.info("pytest_debug_saved", path=str(persistent_debug))

            # Log full output whenever returncode != 0 OR report is missing
            if proc.returncode not in (0, 1) or not report_path.exists():
                logger.warning(
                    "pytest_no_report",
                    returncode=proc.returncode,
                    stdout=stdout_str[-3000:],
                    stderr=stderr_str[-3000:],
                )

            return self._parse_report(report_path, run_id, tests, stdout_str, stderr_str)

    def _parse_report(
        self,
        report_path: Path,
        run_id: UUID,
        tests: list[TestCase],
        stdout_str: str = "",
        stderr_str: str = "",
    ) -> list[TestResult]:
        results: list[TestResult] = []
        if not report_path.exists():
            return results

        try:
            data = json.loads(report_path.read_text())
        except Exception:
            return results

        test_map = {tc.name: tc for tc in tests}

        # Parse individual test results
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

        # Also surface collection errors as failed results so they appear in the count
        if not results:
            for collector in data.get("collectors", []):
                if collector.get("outcome") == "error":
                    longrepr = collector.get("longrepr", "Collection error")
                    results.append(TestResult(
                        run_id=run_id,
                        test_case_id=None,
                        status="error",
                        duration_ms=0,
                        error_message=f"[collection error] {longrepr}",
                        stdout=stdout_str[-1000:] or None,
                        stderr=stderr_str[-1000:] or None,
                    ))

        return results
