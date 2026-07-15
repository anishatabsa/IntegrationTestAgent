# Project Structure

This document describes the layout of the `IntegrationTestAgent` codebase and the responsibility of every directory and key file.

---

## Top-level

```
IntegrationTestAgent/
├── src/aita/          # All application source code
├── tests/             # Automated tests
├── alembic/           # Database migration scripts
├── pyproject.toml     # Project metadata, dependencies, tool config
├── docker-compose.yml # Local infrastructure stack
├── Dockerfile         # Container image for the API and worker
├── alembic.ini        # Alembic migration configuration
├── .env.example       # Template for environment variables
├── .gitignore         # Files excluded from version control
├── setup-mac.sh       # One-command setup script for macOS
├── setup-windows.ps1  # One-command setup script for Windows
└── PROJECT_STRUCTURE.md
```

---

## `src/aita/`

Root Python package. Entry points live here.

| File | Purpose |
|---|---|
| `main.py` | FastAPI application factory (`create_app`). Wires together all adapters, pipeline steps, and the orchestrator during startup via `lifespan`. |
| `worker.py` | Celery worker definition. Wraps `PipelineOrchestrator.run` as an async background task. |
| `config.py` | `Settings` class (pydantic-settings). Reads all environment variables from `.env`. Single source of truth for configuration — import `settings` anywhere. |

---

## `src/aita/domain/`

**Pure business objects — no framework or infrastructure dependencies.**
This layer must never import from `adapters`, `core`, or any third-party library other than the Python standard library.

| File | Purpose |
|---|---|
| `models.py` | Dataclass definitions for every domain concept: `Service`, `EndpointSpec`, `EndpointFingerprint`, `ScannedComponent`, `TestCase`, `PipelineRun`, `TestResult`, `FeedbackItem`, `LearnedPattern`, `KnowledgeDoc`, `RAGContext`. |
| `enums.py` | All enumerations used across the codebase: `Language`, `SpecFormat`, `RunStatus`, `TestStatus`, `FeedbackSource`, `FeedbackType`, `LLMProvider`, `PipelineStep`. |
| `exceptions.py` | Exception hierarchy rooted at `AITAError`. Every subsystem (Git, Spec, Docker, LLM, Healer, Cache, Executor, Reporting, Pipeline) has its own typed exception so callers can catch precisely. |

---

## `src/aita/ports/`

**Hexagonal architecture boundary — abstract interfaces only.**
Nothing in this directory contains logic. The `core` layer depends on these abstractions; `adapters` provide the concrete implementations.

### `ports/inbound/`

Interfaces that **drive** the application (things that call into the core).

| File | Purpose |
|---|---|
| `pipeline_port.py` | `PipelinePort` — `run()`, `run_streaming()`, `get_run()`, `cancel_run()`. Implemented by `PipelineOrchestrator`. |
| `knowledge_port.py` | `KnowledgePort` — `ingest()`, `query()`, `delete_service_knowledge()`. RAG knowledge base management. |

### `ports/outbound/`

Interfaces that the core calls out to (things the core needs from infrastructure).

| File | Purpose |
|---|---|
| `git_port.py` | Clone/pull repos, checkout refs, diff files, commit and push. |
| `llm_port.py` | Send prompts, cache-aware completion, token counting. |
| `cache_port.py` | Get/set/delete keys, distributed locking, pub/sub for SSE events. |
| `docker_port.py` | Find running containers, resolve host URLs, health check. |
| `test_repo_port.py` | Load/save/delete/list generated test cases from the per-service git repository. |
| `allure_port.py` | Upload result files and retrieve report URLs from Allure TestOps. |
| `qmetry_port.py` | Push test results and create test cycles in QMetry. |
| `vector_store_port.py` | Upsert, search, delete, and ensure collections in a vector database. |

---

## `src/aita/core/`

**Application logic — framework-agnostic, depends only on `domain` and `ports`.**

### `core/orchestrator.py`

`PipelineOrchestrator` — implements `PipelinePort`. Runs the 12 pipeline steps in fixed order (Template Method pattern). Supports both blocking (`run`) and SSE-streaming (`run_streaming`) execution modes. Critical steps (`git_pull`, `spec_parse`) abort the run on failure; others log a warning and continue.

### `core/pipeline/`

Everything related to the pipeline's execution model.

| File | Purpose |
|---|---|
| `context.py` | `PipelineContext` — the single mutable object passed between all steps. Holds git output, parsed endpoints, fingerprints, generated tests, results, feedback, and the run summary. Also contains `PipelineOptions` (user-supplied flags) and `StepResult`. |
| `events.py` | SSE event factory functions (`step_started`, `step_completed`, `step_failed`, `pipeline_completed`, `pipeline_failed`, `progress`). Each returns a `PipelineEvent` with a `.to_sse()` method. |
| `base_step.py` | `BaseStep` abstract class. Handles timing, logging, and error wrapping so individual steps only implement `_execute()` and optionally `should_skip()`. |

### `core/pipeline/steps/`

One file per pipeline step. Each file contains a single class extending `BaseStep`.

| File | Step | What it does |
|---|---|---|
| `git_pull_step.py` | 1 — Git Pull | Clones or pulls the service repo to a local directory. |
| `spec_parse_step.py` | 2 — Spec Parse | Detects and parses the API spec (OpenAPI / Swagger / Proto) into `EndpointSpec` objects. |
| `source_scan_step.py` | 3 — Source Scan | Scans service source code to find controllers and their auth/validation annotations. |
| `endpoint_diff_step.py` | 4 — Endpoint Diff | Computes semantic fingerprints for each endpoint and compares against Redis cache to find what changed. |
| `rag_enrich_step.py` | 5 — RAG Enrich | Queries the three-tier RAG engine to build a `RAGContext` of relevant patterns, snippets, and past failures. |
| `generate_step.py` | 6 — Generate | Calls the LLM (with caching) to produce test code for each changed endpoint. |
| `heal_step.py` | 7 — Heal | Runs the 5-stage healer pipeline on every generated test. Drops tests that cannot be repaired. |
| `persist_step.py` | 8 — Persist | Saves healed tests to the per-service git test repository and records the commit SHA. |
| `execute_step.py` | 9 — Execute | Discovers the Docker container, resolves its base URL, and runs the test suite against the live service. |
| `feedback_step.py` | 10 — Feedback | Auto-generates `FeedbackItem` objects from failing results and distils them into `LearnedPattern` objects. |
| `report_step.py` | 11 — Report | Uploads Allure results and pushes test results to QMetry (both optional, controlled by run options). |
| `gate_step.py` | 12 — Gate | Compares pass rate against the configured threshold. Sets run status to `FAILED` if below threshold. |

### `core/spec/`

API specification parsers (Strategy pattern).

| File | Purpose |
|---|---|
| `parser.py` | `BaseSpecParser` abstract class and `SpecParserRegistry`. The registry detects the spec format from the repo directory and returns the right parser. |
| `openapi_parser.py` | Parses OpenAPI 3.x YAML/JSON files into `EndpointSpec` objects. |
| `swagger_parser.py` | Parses Swagger 2.0 YAML/JSON files. Normalises Swagger-2-specific fields to match the common `EndpointSpec` shape. |
| `proto_parser.py` | Parses `.proto` files using regex. Extracts `service` blocks and `rpc` methods as `EndpointSpec` objects with `method = GRPC`. |

### `core/scanner/`

Source code scanners (Strategy pattern). Each scanner is language-specific and produces `ScannedComponent` objects that enrich the fingerprint and the LLM prompt.

| File | Purpose |
|---|---|
| `source_scanner.py` | `BaseSourceScanner` abstract class and `SourceScannerRegistry`. |
| `spring_boot_scanner.py` | Scans Java files for `@RestController` classes. Extracts HTTP method, URL pattern, auth annotations (`@PreAuthorize`, `@Secured`), and validation annotations (`@Valid`, `@NotNull`). |
| `fastapi_scanner.py` | Scans Python files for FastAPI route decorators (`@router.get`, `@app.post`, etc.). Uses the AST to extract route paths and `Depends()` security arguments. |

### `core/fingerprint/`

| File | Purpose |
|---|---|
| `fingerprinter.py` | `EndpointFingerprinter` — computes four independent 8-character xxHash sub-hashes (path, schema, security, source) and combines them into a single `combined_hash`. A change in any dimension triggers LLM regeneration for that endpoint only. |

### `core/generator/`

| File | Purpose |
|---|---|
| `prompt_builder.py` | Assembles the LLM prompt from the endpoint spec, source scan, fingerprint, and RAG context. Injects learned patterns and past failures as instructions to avoid repeating mistakes. |
| `test_generator.py` | `TestGenerator` — calls `LLMPort.complete_cached` to generate test code for one endpoint. Returns `(TestCase, tokens_used)`. |

### `core/healer/`

Five-stage healer pipeline (Chain of Responsibility pattern). Each stage is a `BaseHealerRule` that receives test code and returns a `RuleResult`.

| File | Purpose |
|---|---|
| `healer.py` | `HealerPipeline` — iterates through all rules in order. If any rule sets `dropped=True`, the test is discarded and a feedback item is created. |
| `rules/base_rule.py` | `BaseHealerRule` abstract class and `RuleResult` dataclass. |
| `rules/static_analysis_rule.py` | **Stage 1** — AST-parses Python; invokes `javac` for Java. Fixes truncated `def test` lines and unclosed braces. |
| `rules/rule_based_repair_rule.py` | **Stage 2** — Deterministic string/regex fixes: missing `self.api_client` setup, hardcoded `localhost` URLs, missing `BASE_URL` env reads, Java `RestAssured.baseURI` normalisation. |
| `rules/cross_lang_rule.py` | **Stage 3 (CRITICAL)** — Detects and removes Python code inside Java files and Java code inside Python files. This was the root cause of the most severe failures in the PoC. |
| `rules/semantic_validation_rule.py` | **Stage 4** — Checks that every test method has at least one assertion and that no hardcoded external URLs exist. Annotates issues with `# SEMANTIC_ISSUE:` comments for Stage 5 to act on. |
| `rules/llm_repair_rule.py` | **Stage 5** — Sends annotated code to the LLM for repair. Maximum 2 attempts. If issues remain after all attempts, the test is dropped. |

### `core/knowledge/`

Three-tier RAG system.

| File | Purpose |
|---|---|
| `rag_engine.py` | `RAGEngine` — runs Naive, Agentic, and (optionally) Graph RAG in parallel, fuses results with RRF, then fetches learned patterns and past feedback from the database. Returns a `RAGContext`. |
| `naive_rag.py` | `NaiveRAG` — single-shot dense vector search against Qdrant. |
| `agentic_rag.py` | `AgenticRAG` — multi-hop retrieval. Decomposes compound queries and runs sub-queries independently. Falls back to multi-query vector search when LlamaIndex agent is unavailable. |
| `graph_rag.py` | `GraphRAG` — traverses Neo4j full-text index for entity-relationship context. Active only when `NEO4J_ENABLED=true`. |
| `fusion_ranker.py` | Reciprocal Rank Fusion (RRF). Combines ranked result lists from all RAG tiers into a single de-duplicated, score-ordered list. |
| `ingester.py` | `KnowledgeIngester` — reads Markdown, plain text, RST, and PDF files; chunks them with configurable overlap; upserts into Qdrant with service-name metadata. |

### `core/feedback/`

| File | Purpose |
|---|---|
| `collector.py` | `FeedbackCollector` — classifies failing test results into typed `FeedbackItem` objects. Also provides `from_yaml()` to import QE-authored feedback files. |
| `pattern_learner.py` | `PatternLearner` — counts feedback by type and creates `LearnedPattern` objects with pre-written prompt hints. Patterns are stored in PostgreSQL and surfaced by the RAG engine on future runs. |

### `core/executor/`

| File | Purpose |
|---|---|
| `test_executor.py` | `TestExecutor` abstract base class. |
| `pytest_executor.py` | `PytestExecutor` — writes Python test files to a temp directory, runs `pytest --json-report`, parses results. Optionally writes Allure result files via `--alluredir`. |
| `maven_executor.py` | `MavenExecutor` — scaffolds a minimal `pom.xml` with JUnit 5 + RestAssured, writes Java test files, runs `mvn test`, parses Surefire XML reports. |

---

## `src/aita/adapters/`

**Concrete implementations of all port interfaces.** This is the only layer allowed to import third-party infrastructure libraries.

### `adapters/inbound/rest/routers/`

FastAPI route handlers. Each file is a separate `APIRouter` mounted in `main.py`.

| File | Prefix | Purpose |
|---|---|---|
| `runs.py` | `/api/v1/runs` | Trigger pipeline runs, stream SSE events, poll run status. |
| `services.py` | `/api/v1/services` | Register, list, and delete services. |
| `knowledge.py` | `/api/v1/knowledge` | Ingest documents, query the knowledge base, delete service knowledge. |
| `webhooks.py` | `/api/v1/webhooks` | Receive GitLab push events (`/gitlab`) and Jenkins post-build notifications (`/jenkins`). Validates HMAC signatures before triggering runs. |

### `adapters/inbound/cli/`

Typer CLI with Rich terminal output.

| File | Purpose |
|---|---|
| `main.py` | CLI entry point. Commands: `run`, `ingest`, `import-feedback`, `list`. Streams SSE events from the API and renders them with Rich progress panels. |
| `display.py` | Rich display helpers — `stream_events()` connects to the SSE endpoint and renders step-by-step progress; `print_summary()` prints the final pass/fail panel. |

### `adapters/outbound/`

| File | Implements | Technology |
|---|---|---|
| `git_adapter.py` | `GitPort` | gitpython + tenacity retry |
| `anthropic_adapter.py` | `LLMPort` | Anthropic Python SDK + Redis cache |
| `ollama_adapter.py` | `LLMPort` | httpx → Ollama REST API + Redis cache |
| `redis_adapter.py` | `CachePort` | redis-py asyncio |
| `qdrant_adapter.py` | `VectorStorePort` | qdrant-client asyncio |
| `docker_adapter.py` | `DockerPort` | docker-py SDK + httpx health check |
| `git_test_repo.py` | `TestRepoPort` | gitpython — one local git repo per service under `test-repos/` |
| `allure_adapter.py` | `AllurePort` | httpx → Allure Docker Service REST API |
| `qmetry_adapter.py` | `QMetryPort` | httpx → QMetry REST API v1 |
| `postgres/models.py` | — | SQLAlchemy 2 ORM mapped classes mirroring the domain models |

---

## `src/aita/shared/`

Cross-cutting utilities that any layer may import.

| File | Purpose |
|---|---|
| `logging.py` | `configure_logging()` — sets up structlog with JSON output in production and coloured console output when running interactively. |

---

## `alembic/`

Database migration management (Alembic + asyncpg).

| Path | Purpose |
|---|---|
| `env.py` | Alembic environment script. Wires `Base.metadata` from the ORM models and runs migrations asynchronously via `asyncpg`. |
| `versions/001_initial_schema.py` | Initial migration — creates all 7 tables (`services`, `endpoints`, `test_cases`, `pipeline_runs`, `test_results`, `feedback_items`, `learned_patterns`, `knowledge_docs`) with indexes. |

---

## `tests/`

### `tests/unit/`

Fast, dependency-free tests. No database, no network, no LLM calls.

| File | What it tests |
|---|---|
| `test_fingerprinter.py` | Determinism, sensitivity to endpoint changes, hash length. |
| `test_cross_lang_rule.py` | Python-in-Java detection and removal; Java-in-Python detection and removal; clean code passes unchanged. |
| `test_fusion_ranker.py` | Single-list order preservation, inter-list agreement promotion, deduplication, empty inputs. |
| `test_openapi_parser.py` | Endpoint count, operation IDs, method/path/parameter/response fields. |
| `test_pattern_learner.py` | Empty feedback, most-common-type ranking, prompt snippet population. |

### `tests/integration/`

End-to-end tests that require running infrastructure (Redis, Postgres, a live service). Populated as features are built out.

---

## Key design decisions at a glance

| Decision | Where it lives |
|---|---|
| Hexagonal Architecture (Ports & Adapters) | `ports/` ↔ `core/` ↔ `adapters/` |
| Template Method — fixed 12-step pipeline | `core/orchestrator.py` + `core/pipeline/steps/` |
| Strategy — pluggable parsers and scanners | `core/spec/parser.py`, `core/scanner/source_scanner.py` |
| Chain of Responsibility — 5-stage healer | `core/healer/healer.py` + `core/healer/rules/` |
| Observer / SSE event bus | `core/pipeline/events.py` + `adapters/inbound/rest/routers/runs.py` |
| Three-level cache | Redis (fingerprints + LLM responses) + Git test repo (persisted tests) |
| Three-tier RAG + RRF fusion | `core/knowledge/` |
