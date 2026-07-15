"""
Core domain models — pure Python dataclasses, no ORM / infrastructure deps.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from aita.domain.enums import (
    FeedbackSource,
    FeedbackType,
    Language,
    RunStatus,
    SpecFormat,
    TestStatus,
)


@dataclass
class Service:
    name: str
    repo_url: str
    language: Language
    spec_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None


@dataclass
class EndpointSpec:
    """Parsed representation of a single API endpoint."""
    operation_id: str
    method: str
    path: str
    summary: str = ""
    parameters: list[dict[str, Any]] = field(default_factory=list)
    request_body: dict[str, Any] | None = None
    responses: dict[str, Any] = field(default_factory=dict)
    security: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class EndpointFingerprint:
    """Multi-hash fingerprint used for change detection."""
    operation_id: str
    combined_hash: str          # XOR / concat of sub-hashes
    path_hash: str
    schema_hash: str
    security_hash: str
    source_hash: str
    computed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ScannedComponent:
    """A testable component found by the source scanner."""
    operation_id: str
    controller_class: str
    method_name: str
    http_method: str
    url_pattern: str
    auth_annotations: list[str] = field(default_factory=list)
    validation_annotations: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestCase:
    endpoint_id: uuid.UUID
    name: str
    content: str
    language: Language
    status: TestStatus = TestStatus.GENERATED
    git_ref: str | None = None
    fingerprint_at_generation: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None


@dataclass
class PipelineRun:
    service_id: uuid.UUID
    status: RunStatus = RunStatus.PENDING
    branch: str | None = None
    commit_sha: str | None = None
    triggered_by: str = "manual"
    options: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TestResult:
    run_id: uuid.UUID
    status: str
    test_case_id: uuid.UUID | None = None
    duration_ms: int | None = None
    error_message: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FeedbackItem:
    source: FeedbackSource
    feedback_type: FeedbackType
    description: str
    run_id: uuid.UUID | None = None
    endpoint_id: uuid.UUID | None = None
    fix_hint: str | None = None
    applied: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class LearnedPattern:
    pattern_type: str
    description: str
    service_id: uuid.UUID | None = None
    pattern_key: str | None = None
    prompt_snippet: str | None = None
    occurrence_count: int = 1
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    last_seen_at: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class KnowledgeDoc:
    source_path: str
    content_hash: str
    service_id: uuid.UUID | None = None
    doc_type: str | None = None
    qdrant_ids: list[str] = field(default_factory=list)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    ingested_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RAGContext:
    """Enrichment context passed to the test generator."""
    patterns: list[LearnedPattern] = field(default_factory=list)
    feedback_items: list[FeedbackItem] = field(default_factory=list)
    knowledge_snippets: list[str] = field(default_factory=list)
    similar_tests: list[str] = field(default_factory=list)
