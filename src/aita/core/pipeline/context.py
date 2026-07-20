"""
Pipeline execution context — the single mutable object that flows through all steps.
Implements the Saga pattern: checkpointed state that can be resumed after failure.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from aita.domain.enums import PipelineStep, RunStatus
from aita.domain.models import (
    EndpointFingerprint,
    EndpointSpec,
    FeedbackItem,
    LearnedPattern,
    PipelineRun,
    RAGContext,
    ScannedComponent,
    TestCase,
    TestResult,
)


@dataclass
class PipelineOptions:
    """User-supplied options that control pipeline behaviour."""
    service_name: str
    branch: str = "main"
    force_generate: bool = False    # bypass endpoint fingerprint cache
    ignore_cache: bool = False      # bypass LLM response cache
    learn_from_kb: bool = True      # enrich prompts with RAG context
    update_kb: bool = False         # ingest spec + source into KB after parse
    selected_operations: list[str] = field(default_factory=list)  # empty = all
    run_tests: bool = True
    push_to_allure: bool = False
    push_to_qmetry: bool = False
    triggered_by: str = "manual"    # manual | gitlab | jenkins | cli
    extra: dict[str, Any] = field(default_factory=dict)

    # ── Inline service config (used when no DB service registry entry exists) ─
    # Allows triggering a run without pre-registering the service via /api/v1/services.
    repo_url: str = ""       # git clone URL or file:// local path
    base_url: str = ""       # running service base URL (e.g. http://localhost:8001)
    language: str = "python" # python | java
    spec_url: str = ""       # fetch OpenAPI spec from this URL (e.g. /openapi.json on base_url)

    # ── Test automation repo (GitHub PR publishing) ───────────────────────────
    test_automation_repo_url: str = ""   # e.g. https://github.com/org/integration-test-automation
    test_automation_branch: str = "main" # default branch of the automation repo
    publish_on_gate_pass: bool = True    # only publish when quality gate passes


@dataclass
class StepResult:
    step: PipelineStep
    status: str                     # success | skipped | failed
    message: str = ""
    duration_ms: int = 0
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineContext:
    """Mutable shared state carried by the pipeline from step 1 to step 12."""
    run_id: uuid.UUID = field(default_factory=uuid.uuid4)
    options: PipelineOptions = field(default_factory=lambda: PipelineOptions(service_name=""))

    # ── Run record ───────────────────────────────────────────────────────────
    run: PipelineRun | None = None
    status: RunStatus = RunStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None

    # ── Step results (ordered) ────────────────────────────────────────────────
    step_results: list[StepResult] = field(default_factory=list)

    # ── Git ──────────────────────────────────────────────────────────────────
    repo_dir: Path | None = None
    commit_sha: str | None = None

    # ── Spec ─────────────────────────────────────────────────────────────────
    raw_spec: dict[str, Any] | None = None
    endpoints: list[EndpointSpec] = field(default_factory=list)

    # ── Source scan ──────────────────────────────────────────────────────────
    scanned_components: list[ScannedComponent] = field(default_factory=list)

    # ── Fingerprints ─────────────────────────────────────────────────────────
    fingerprints: dict[str, EndpointFingerprint] = field(default_factory=dict)   # op_id → fp
    changed_operations: list[str] = field(default_factory=list)

    # ── RAG ──────────────────────────────────────────────────────────────────
    rag_context: RAGContext | None = None

    # ── Existing tests (fetched from automation repo before generation) ──────
    existing_tests: dict[str, str] = field(default_factory=dict)                 # op_id → file content

    # ── Generated / healed tests ─────────────────────────────────────────────
    generated_tests: dict[str, TestCase] = field(default_factory=dict)           # op_id → test
    healed_tests: dict[str, TestCase] = field(default_factory=dict)

    # ── Execution ────────────────────────────────────────────────────────────
    test_results: list[TestResult] = field(default_factory=list)
    allure_report_url: str | None = None
    qmetry_cycle_key: str | None = None

    # ── Publish ───────────────────────────────────────────────────────────────
    pr_url: str | None = None

    # ── Feedback & learning ───────────────────────────────────────────────────
    feedback_items: list[FeedbackItem] = field(default_factory=list)
    learned_patterns: list[LearnedPattern] = field(default_factory=list)

    # ── Summary ──────────────────────────────────────────────────────────────
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    token_usage: dict[str, int] = field(default_factory=dict)  # step → tokens

    def add_step_result(self, result: StepResult) -> None:
        self.step_results.append(result)

    def fail(self, message: str) -> None:
        self.status = RunStatus.FAILED
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def summary(self) -> dict[str, Any]:
        passing = sum(1 for r in self.test_results if r.status == "passed")
        errors = sum(1 for r in self.test_results if r.status == "error")
        total = len(self.test_results)
        return {
            "run_id": str(self.run_id),
            "status": self.status,
            "endpoints_total": len(self.endpoints),
            "endpoints_changed": len(self.changed_operations),
            "tests_generated": len(self.generated_tests),
            "tests_healed": len(self.healed_tests),
            "tests_passing": passing,
            "tests_errors": errors,
            "tests_total": total,
            "pass_rate": round(passing / total * 100, 1) if total else 0,
            "token_usage": self.token_usage,
            "pr_url": self.pr_url,
            "errors": self.errors,
            "warnings": self.warnings,
        }
