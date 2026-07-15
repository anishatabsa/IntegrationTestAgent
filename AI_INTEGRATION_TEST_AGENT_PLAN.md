# AI Integration Test Agent — Implementation Plan v1.0

> **Status:** Draft · Last updated: 2026-07-15  
> **Purpose:** Reference document for building the production-grade AI Integration Test Agent from scratch. Update this document before building each feature.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Technology Stack](#3-technology-stack)
4. [Component Design](#4-component-design)
5. [Data Models](#5-data-models)
6. [Caching Strategy](#6-caching-strategy)
7. [RAG Enhancement Strategy](#7-rag-enhancement-strategy)
8. [API Design](#8-api-design)
9. [CI/CD Integration](#9-cicd-integration)
10. [Healer Design](#10-healer-design)
11. [Test Repository Strategy](#11-test-repository-strategy)
12. [Reporting & Test Management](#12-reporting--test-management)
13. [Deployment & Setup](#13-deployment--setup)
14. [Design Patterns Applied](#14-design-patterns-applied)
15. [Phase-by-Phase Delivery Plan](#15-phase-by-phase-delivery-plan)
16. [Open Questions & Decisions](#16-open-questions--decisions)

---

## 1. Executive Summary

The AI Integration Test Agent automatically generates, heals, executes, and learns from integration tests for any service that exposes a machine-readable specification (OpenAPI, Swagger, gRPC proto). This rebuild targets production use on real live services with the following goals:

- **Zero-touch CI**: trigger from GitLab or Jenkins, get a pass/fail back
- **Local-first DX**: a rich CLI client for engineers to explore, override, and learn
- **Minimal token burn**: LLM is called only when cached knowledge is insufficient
- **Self-improving**: every run enriches the knowledge base so the next run is cheaper and smarter
- **Portable**: deployable on-prem, no cloud dependency required

---

## 2. Architecture Overview

### 2.1 Architectural Pattern — Hexagonal (Ports & Adapters)

```
┌─────────────────────────────────────────────────────────────────┐
│                        DRIVING SIDE                             │
│   CLI Client │ REST API │ GitLab Hook │ Jenkins Hook            │
└──────────────────────────┬──────────────────────────────────────┘
                           │  Ports (inbound)
┌──────────────────────────▼──────────────────────────────────────┐
│                    APPLICATION CORE                             │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Orchestrator│  │  Test Engine │  │   Knowledge Engine   │  │
│  │  (Pipeline) │  │  (Gen/Heal/  │  │  (RAG + Learning)    │  │
│  │             │  │   Execute)   │  │                      │  │
│  └─────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Spec       │  │  Source      │  │   Feedback &         │  │
│  │  Parser     │  │  Scanner     │  │   Pattern Learner    │  │
│  └─────────────┘  └──────────────┘  └──────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │  Ports (outbound)
┌──────────────────────────▼──────────────────────────────────────┐
│                      DRIVEN SIDE (Adapters)                     │
│                                                                 │
│  Git Adapter │ Docker Adapter │ LLM Adapter │ Cache Adapter     │
│  Test Repo   │ Allure Adapter │ QMetry Adap │ Notification Adap │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Layer Breakdown

| Layer | Responsibility |
|---|---|
| **Inbound Adapters** | CLI, FastAPI REST, GitLab/Jenkins webhook receivers |
| **Application Core** | Orchestration, generation, healing, learning — pure business logic, no I/O |
| **Domain Models** | Service, Endpoint, TestCase, FeedbackItem, LearnedPattern |
| **Outbound Adapters** | Git, Docker, LLM providers, Redis, PostgreSQL, Allure, QMetry |

### 2.3 Process Flow

```
Trigger (CI / CLI / API)
    │
    ▼
1. Pull source from Git (branch-aware)
    │
    ▼
2. Parse spec files (OpenAPI / proto / Swagger)
    │
    ▼
3. Scan source code → detect integration test candidates
    │
    ▼
4. Diff against cached endpoint fingerprints (Redis)
    │  unchanged → skip LLM, load from Test Repository
    │  changed   → continue
    ▼
5. Enrich prompt with RAG context (Naive + Graph + Agentic)
    │
    ▼
6. LLM generates test blocks (endpoint-level, parallel)
    │
    ▼
7. Healer validates, repairs, rejects broken tests
    │
    ▼
8. Write tests to Test Repository (Git/DB)
    │
    ▼
9. Execute tests against target (live / Docker)
    │
    ▼
10. Collect results → store feedback → update patterns
    │
    ▼
11. Push to Allure Server + QMetry
    │
    ▼
12. Return pass/fail to trigger
```

### 2.4 Async Processing Model

Long-running steps (Git pull, LLM generation, test execution) run as async tasks:

```
FastAPI endpoint → enqueue Celery task → Redis broker
                                              │
                             Worker picks up → executes → updates DB
                                              │
                             SSE / WebSocket → streams progress to client
```

---

## 3. Technology Stack

| Concern | Choice | Rationale |
|---|---|---|
| Core language | Python 3.12 | Ecosystem, LLM library support |
| Service layer | FastAPI + uvicorn | Async, OpenAPI auto-docs, fast |
| Task queue | Celery 5 + Redis | Mature, distributed, retry logic |
| Cache | Redis 7 | Pub/sub + cache + Celery broker in one |
| Test repo DB | PostgreSQL 16 | JSONB for flexible test metadata |
| Test file storage | Git (bare repo) | Version history, diff, branch per service |
| LLM (primary) | Anthropic Claude API | Best code generation quality |
| LLM (local/fallback) | Ollama (configurable model) | On-prem option, no API key needed |
| RAG framework | LlamaIndex | Naive, Graph, and Agentic RAG support |
| Vector store | Qdrant | On-prem, fast, good Python SDK |
| Graph RAG | Neo4j (optional) | Relationship-aware retrieval |
| CLI client | Typer + Rich | Beautiful terminal UX |
| CI adapter | REST API + Webhooks | GitLab/Jenkins native |
| Container runtime | Docker SDK for Python | Detect and connect to Docker Desktop |
| Test framework (Python) | pytest | Established, plugin-rich |
| Test framework (Java) | JUnit 5 + REST-assured | Spring Boot integration tests |
| Reporting | Allure TestOps API | Centralized report server |
| Test management | QMetry REST API / MCP | Test case sync |
| State machine (future) | LangGraph | Ready for LangGraph migration |
| Pipeline framework (future) | Haystack | Document pipeline extension |
| Setup tooling | shell scripts + Docker Compose | One-command install |
| Containerisation | Docker + Docker Compose | All services packaged |

---

## 4. Component Design

### 4.1 Orchestrator

The central pipeline coordinator. Implements the **Template Method** pattern: a fixed pipeline skeleton with pluggable steps.

```python
class PipelineOrchestrator:
    steps: list[PipelineStep]   # ordered, each step is a port
    context: PipelineContext    # shared state bag passed through steps
    event_bus: EventBus         # emits progress events to SSE/WS clients

    async def run(self, trigger: TriggerRequest) -> PipelineResult: ...
```

**Steps (in order):**
1. `GitPullStep` — clone/fetch repo, checkout branch
2. `SpecParseStep` — find and parse OpenAPI/proto/Swagger
3. `SourceScanStep` — scan source, detect components
4. `EndpointDiffStep` — fingerprint endpoints, compare to cache
5. `RAGEnrichStep` — build LLM context from knowledge base
6. `GenerateStep` — call LLM per changed endpoint (parallel)
7. `HealStep` — validate and repair generated tests
8. `PersistStep` — write tests to Test Repository
9. `ExecuteStep` — run tests against target service
10. `FeedbackStep` — collect results, store patterns
11. `ReportStep` — push to Allure + QMetry
12. `GateStep` — evaluate quality gate, return result

Each step implements:

```python
class PipelineStep(ABC):
    @abstractmethod
    async def execute(self, ctx: PipelineContext) -> StepResult: ...

    async def on_error(self, ctx: PipelineContext, exc: Exception) -> StepResult:
        # default: log + mark step failed + continue or halt per config
```

**Graceful failure**: every step catches its own exceptions, sets `ctx.step_errors[step_name]`, and the orchestrator decides whether to halt or skip to the next step based on step criticality. Non-critical steps (e.g., QMetry push) never halt the pipeline.

---

### 4.2 Git Adapter

```python
class GitAdapter(RepositoryPort):
    def clone_or_fetch(self, repo_url: str, branch: str, target_dir: Path) -> None: ...
    def get_changed_files(self, base_ref: str, head_ref: str) -> list[str]: ...
    def find_spec_files(self, repo_dir: Path) -> list[SpecFile]: ...
```

- Uses `gitpython` library
- Supports SSH and HTTPS with credentials from env/vault
- `find_spec_files` searches for `openapi.yaml`, `swagger.yaml`, `*.proto`, `openapi.json` recursively
- Branch name is taken from `TriggerRequest.branch` (CI injects this) or CLI `--branch` flag
- **Fails gracefully**: if clone fails, raises `GitAdapterError` with clean message; pipeline logs and halts `GitPullStep` which is critical

---

### 4.3 Spec Parser

```python
class SpecParser:
    parsers: dict[SpecType, SpecParserStrategy]  # Strategy pattern

    def parse(self, spec_file: SpecFile) -> ServiceSpec: ...
```

**Strategies:**
- `OpenApiParser` — handles YAML/JSON OpenAPI 3.x and Swagger 2.x
- `ProtoParser` — parses `.proto` files, extracts services/methods/messages
- `GraphQLParser` — (future) parses `.graphql` schema

`ServiceSpec` is the unified internal model regardless of source format:

```python
@dataclass
class ServiceSpec:
    service_name: str
    service_type: ServiceType          # REST | GRPC | GRAPHQL
    base_url: str | None
    endpoints: list[EndpointSpec]
    schemas: dict[str, JsonSchema]     # shared schema definitions
    security_schemes: list[SecurityScheme]
```

---

### 4.4 Source Scanner

Scans the actual service source code to detect implementation details not captured in the spec, such as custom validators, middleware, authentication guards, and database interactions.

```python
class SourceScanner:
    strategies: list[ScanStrategy]    # per language/framework

    def scan(self, repo_dir: Path, spec: ServiceSpec) -> ScanResult: ...
```

**Detection targets by framework:**

| Framework | Detected |
|---|---|
| Spring Boot | `@RestController`, `@PreAuthorize`, `@Valid`, `@Validated`, filter beans |
| FastAPI | `Depends()`, Pydantic validators, middleware, security schemes |
| Express.js | Router handlers, middleware chains, Joi/Zod validators |
| gRPC (any) | Interceptors, auth metadata, error codes |

`ScanResult` enriches the prompt context with implementation-specific hints, reducing hallucination.

---

### 4.5 Endpoint Fingerprinting & Diff

Replaces the current file-hash approach with a **semantic fingerprint**:

```python
@dataclass
class EndpointFingerprint:
    operation_id: str
    path_hash: str          # hash of path + method
    schema_hash: str        # hash of request/response schemas
    security_hash: str      # hash of security requirements
    scan_hash: str          # hash of source scan result for this endpoint
    combined_hash: str      # SHA-256 of all above
    last_seen: datetime
    last_generated: datetime
    test_count: int
```

Stored in Redis with key: `fingerprint:{service}:{operation_id}`

**Change detection logic:**
- `combined_hash` changed → full regen
- Only `scan_hash` changed → targeted regen (implementation changed but spec same)
- Only `security_hash` changed → regenerate auth-related tests only
- No change → load from Test Repository, skip LLM

This eliminates the current problem of regenerating everything because the spec hash changed.

---

### 4.6 LLM Adapter

```python
class LLMAdapter(LLMPort):
    provider: LLMProvider   # ANTHROPIC | OLLAMA | OPENAI | AZURE_OPENAI

    async def generate(self, prompt: Prompt) -> GenerationResult: ...
    async def heal(self, broken_code: str, errors: list[str]) -> HealResult: ...
```

**Token optimization strategies (requirement #14):**
1. **Fingerprint diff**: only call LLM for changed endpoints (already described)
2. **Prompt compression**: strip redundant schema definitions, inline only what's needed
3. **Batch generation**: one LLM call per file (not per endpoint) where endpoints are related
4. **Result caching**: cache LLM responses in Redis with TTL=24h keyed by prompt hash
5. **Incremental healing**: healer uses rule engine first (no LLM cost); LLM healer invoked only when rules fail
6. **Model routing**: use cheaper/smaller model for healing simple syntax errors; full model for generation

---

### 4.7 Test Generator

```python
class TestGenerator:
    llm: LLMAdapter
    rag: RAGEngine
    prompt_builder: PromptBuilder

    async def generate_for_endpoint(
        self,
        endpoint: EndpointSpec,
        scan_result: ScanResult,
        rag_context: RAGContext,
        existing_feedback: list[FeedbackItem],
        learned_patterns: list[LearnedPattern],
    ) -> GeneratedTestBlock: ...
```

**Parallel generation**: endpoints are processed concurrently using `asyncio.gather`, with a configurable semaphore to limit concurrent LLM calls (e.g., max 5 at once).

**Prompt structure:**
```
[SYSTEM CONTEXT]
  - Service type, language, test framework
  - Learned patterns (from knowledge base)
  - QE feedback for this operation (if any)

[SPECIFICATION]
  - Endpoint: method, path, parameters, request/response schemas
  - Security requirements

[SOURCE HINTS]
  - Detected validators, middleware, guards

[RAG CONTEXT]
  - Similar endpoints from knowledge base
  - Domain-specific test patterns

[INSTRUCTION]
  - Generate N test methods covering: happy path, boundary values,
    error cases, auth scenarios, flow dependencies
  - Follow [framework] conventions strictly
  - Output ONLY the test methods, no class wrapper
```

---

### 4.8 Healer

See dedicated section [§10](#10-healer-design).

---

### 4.9 CLI Client

Built with **Typer** + **Rich** for a polished terminal experience.

```
Usage: aita [OPTIONS] COMMAND [ARGS]...

Commands:
  run          Execute the full pipeline for one or more services
  generate     Generate tests only (no execution)
  execute      Execute existing tests only (no generation)
  heal         Run healer only on existing test files
  learn        Import knowledge documents into the knowledge base
  feedback     Import QE feedback YAML
  cache        Manage the cache (inspect / evict / flush)
  status       Show last pipeline run status
  services     List configured services and their status
  config       View or set configuration
  setup        Interactive first-run setup wizard
```

**Key options for `run`:**

```
aita run --service ecommerce
         --branch feature/new-endpoint
         --force-regen                  # bypass cache, always call LLM
         --ignore-cache                 # don't read from cache (but write)
         --services ecommerce,inventory # comma-separated multi-service
         --target docker://myapp:8080   # run against local Docker container
         --target http://localhost:8765 # run against local process
         --skip-execute                 # generate only, don't run
         --skip-learn                   # don't update knowledge base after run
         --dry-run                      # plan only, print what would happen
         --watch                        # stream live progress
```

**`learn` command:**
```
aita learn --from docs/api-guide.pdf
aita learn --from docs/
aita learn --from https://confluence.example.com/page/12345
aita learn --show                      # display current knowledge base entries
aita learn --purge domain-name         # remove a knowledge domain
```

**`feedback` command:**
```
aita feedback --import qe_feedback.yaml
aita feedback --list --service ecommerce
aita feedback --mark-applied fb-id-123
```

**`cache` command:**
```
aita cache --list
aita cache --evict --service inventory --operation createWarehouse
aita cache --flush --service ecommerce
aita cache --stats
```

---

### 4.10 Progress & Event Streaming (Requirement #13)

Every pipeline step emits structured events:

```python
@dataclass
class PipelineEvent:
    run_id: str
    step: str
    status: EventStatus     # STARTED | PROGRESS | COMPLETED | FAILED | SKIPPED
    message: str
    detail: dict            # step-specific payload
    timestamp: datetime
    progress_pct: int | None
```

**Delivery mechanisms:**
- **CLI**: Rich `Live` panel with step progress table, real-time log tail
- **REST API**: Server-Sent Events (SSE) on `GET /runs/{run_id}/events`
- **CI**: printed to stdout in structured log format (GitLab/Jenkins parse it)
- **WebSocket**: optional for web dashboard (future)

---

## 5. Data Models

### 5.1 Core Domain Models

```python
@dataclass
class Service:
    id: UUID
    name: str
    type: ServiceType           # REST | GRPC | GRAPHQL
    repo_url: str
    default_branch: str
    spec_path: str | None       # relative path in repo, or None = auto-detect
    target_url: str | None      # override for execution target
    created_at: datetime

@dataclass
class EndpointSpec:
    operation_id: str
    method: str
    path: str
    parameters: list[Parameter]
    request_body: JsonSchema | None
    responses: dict[str, JsonSchema]
    security: list[str]
    tags: list[str]
    deprecated: bool

@dataclass
class TestCase:
    id: UUID
    service_id: UUID
    operation_id: str
    name: str
    framework: TestFramework    # PYTEST | JUNIT5 | JEST
    language: Language          # PYTHON | JAVA | TYPESCRIPT
    source_code: str
    fingerprint_hash: str       # endpoint fingerprint when generated
    status: TestStatus          # ACTIVE | DEPRECATED | DISABLED
    pass_rate_7d: float | None
    created_at: datetime
    updated_at: datetime

@dataclass
class FeedbackItem:
    id: UUID
    service_id: UUID
    operation_id: str
    type: FeedbackType          # BOUNDARY_MISSED | MISSING_SCENARIO | WRONG_ASSERTION | etc.
    priority: Priority
    description: str
    example_test_name: str | None
    test_data_hints: dict
    applied: bool
    applied_at: datetime | None
    created_at: datetime

@dataclass
class LearnedPattern:
    id: UUID
    name: str
    description: str
    applies_to: list[str]       # operation_ids or tags or ['*']
    pattern_code: str
    confidence: float
    usage_count: int
    source: str                 # QE_FEEDBACK | AUTO_LEARNED | MANUAL

@dataclass
class PipelineRun:
    id: UUID
    service_id: UUID
    branch: str
    trigger_type: TriggerType   # CLI | API | GITLAB | JENKINS
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None
    step_results: dict[str, StepResult]
    test_summary: TestSummary | None
    quality_gate: QualityGateResult | None
```

### 5.2 Database Schema

**PostgreSQL tables:**
- `services` — registered services
- `pipeline_runs` — run history with JSONB step results
- `test_cases` — generated test code and metadata
- `feedback_items` — QE feedback
- `learned_patterns` — auto and manual learned patterns
- `endpoint_test_mappings` — which test cases cover which endpoints

**Redis keys:**
- `fingerprint:{service_name}:{operation_id}` → JSON fingerprint
- `llm_cache:{prompt_hash}` → LLM response (TTL 24h)
- `run:{run_id}:events` → SSE event list (pub/sub channel)
- `run:{run_id}:status` → current run status
- `lock:generate:{service}:{operation_id}` → distributed lock during generation

---

## 6. Caching Strategy

### 6.1 Two-Level Cache Architecture

```
Level 1 — Endpoint Fingerprint Cache (Redis)
  Purpose: decide whether to call LLM at all
  Key:     fingerprint:{service}:{operation_id}
  TTL:     no expiry (evicted on spec change detection)
  Size:    small (< 1 KB per entry)

Level 2 — LLM Response Cache (Redis)
  Purpose: avoid duplicate LLM calls for identical prompts
  Key:     llm:{sha256(prompt)}
  TTL:     24 hours (prompts change as patterns evolve)
  Size:    medium (1-20 KB per entry, configurable max)

Level 3 — Test Repository (PostgreSQL + Git)
  Purpose: persist generated tests across runs, serve unchanged endpoints
  Key:     test_cases table + git commit per run
  TTL:     permanent until deprecated by fingerprint change
  Size:    unlimited
```

### 6.2 Cache Invalidation Rules

| Trigger | Action |
|---|---|
| Endpoint spec changed | Evict Level 1 fingerprint, evict Level 2 for that endpoint's prompts |
| Source scan changed (implementation only) | Evict Level 1, keep Level 2 unless prompt changes |
| `--force-regen` flag | Bypass Level 1 and Level 2, always call LLM |
| `--ignore-cache` flag | Bypass Level 1 read (but still write after generation) |
| `aita cache --evict` | Manually evict specific entry |
| Feedback imported for operation_id | Evict Level 1 for that operation (force regen with new feedback) |

### 6.3 Redis Configuration

```yaml
redis:
  host: localhost
  port: 6379
  db: 0
  max_memory: 512mb
  max_memory_policy: allkeys-lru    # evict least-recently-used when full
  key_prefix: "aita:"
```

---

## 7. RAG Enhancement Strategy

### 7.1 Three-Tier RAG

The knowledge engine uses three complementary retrieval strategies, combined by a **fusion ranker**:

```
Query (endpoint spec + context)
    │
    ├─► Naive RAG          → top-k similar chunks from vector store
    │   (Qdrant)              (fast, broad recall)
    │
    ├─► Graph RAG           → traverse entity relationships
    │   (Neo4j, optional)     (e.g., "Customer → Order → Product" test chains)
    │
    └─► Agentic RAG         → LLM decides what to retrieve
        (LlamaIndex Agent)    (for complex queries needing multi-hop reasoning)
    │
    ▼
Fusion Ranker (RRF — Reciprocal Rank Fusion)
    │
    ▼
RAG Context (injected into generation prompt)
```

### 7.2 Knowledge Base Population

**Sources accepted by `aita learn`:**

| Source Type | Handling |
|---|---|
| Markdown (`.md`) | Split by heading, embed, store in Qdrant |
| PDF | PyMuPDF extraction → chunk → embed → Qdrant |
| Plain text | Chunk → embed → Qdrant |
| OpenAPI YAML/JSON | Parse endpoints → embed each operation → Qdrant |
| Confluence URL | Fetch via REST API → HTML → markdown → chunk → embed |
| Past test runs | Extract passing test patterns → LearnedPattern records |
| QE feedback | Structured → FeedbackItem → also embed description for RAG |

**Embedding model:** `text-embedding-3-small` (OpenAI) or `nomic-embed-text` (Ollama, on-prem).

### 7.3 Agentic RAG Flow

For complex endpoint contexts, the Agentic RAG agent is given tools:

```python
tools = [
    search_similar_endpoints,       # find similar endpoints in KB
    search_test_patterns,           # find relevant test patterns
    search_domain_knowledge,        # search docs/PDFs
    get_past_failures_for_endpoint, # retrieve failure history
    get_learned_patterns,           # get applicable patterns
]
```

The agent constructs a multi-hop context (e.g., "find auth patterns → find error handling patterns → find data dependency patterns for this endpoint").

### 7.4 Pattern Learning (Requirement #4)

After every run, the Pattern Learner runs:

1. **Failure analysis**: for each failed test, determine root cause category (wrong status, wrong schema, auth not enforced, data dependency, etc.)
2. **Pattern extraction**: if the same root cause appears across ≥3 endpoints, create a `LearnedPattern` record
3. **Confidence scoring**: pattern confidence = (times it prevented a failure) / (times it was applied)
4. **Feedback loop**: patterns feed into the next run's prompt, reducing the same class of mistake

**Anti-patterns** are also stored — things Claude generated that consistently failed — so they are explicitly excluded from future prompts.

---

## 8. API Design

### 8.1 REST API (FastAPI)

Base path: `/api/v1`

**Runs:**

```
POST   /runs                         # trigger a pipeline run
GET    /runs                         # list recent runs
GET    /runs/{run_id}                # get run details
GET    /runs/{run_id}/events         # SSE stream of run events
DELETE /runs/{run_id}                # cancel a running pipeline
```

**Services:**

```
POST   /services                     # register a service
GET    /services                     # list services
GET    /services/{service_id}        # service details
PUT    /services/{service_id}        # update service config
DELETE /services/{service_id}        # remove service
```

**Tests:**

```
GET    /services/{service_id}/tests  # list generated tests
GET    /tests/{test_id}              # get test source
PUT    /tests/{test_id}/disable      # disable a test
DELETE /tests/{test_id}              # remove a test
```

**Knowledge Base:**

```
POST   /knowledge/import             # import document(s) into KB
GET    /knowledge                    # list KB entries
DELETE /knowledge/{entry_id}         # remove KB entry
POST   /knowledge/purge              # purge a domain
```

**Feedback:**

```
POST   /feedback/import              # import QE feedback YAML
GET    /feedback                     # list feedback items
PUT    /feedback/{id}/apply          # manually mark applied
```

**Cache:**

```
GET    /cache/stats                  # cache statistics
DELETE /cache/service/{name}         # flush service cache
DELETE /cache/endpoint/{name}/{op}   # evict one endpoint
```

**Webhooks (CI integration):**

```
POST   /hooks/gitlab                 # GitLab pipeline webhook
POST   /hooks/jenkins                # Jenkins post-build webhook
```

### 8.2 Webhook Payload — GitLab

```json
{
  "object_kind": "pipeline",
  "project": { "git_http_url": "https://gitlab.example.com/org/service.git" },
  "ref": "feature/my-branch",
  "sha": "abc123",
  "aita": {
    "services": ["ecommerce"],
    "force_regen": false,
    "quality_gate_threshold": 80
  }
}
```

### 8.3 Quality Gate Response

```json
{
  "run_id": "uuid",
  "status": "PASS" | "FAIL",
  "summary": {
    "total": 238,
    "passed": 210,
    "failed": 28,
    "broken": 0,
    "pass_rate": 88.2
  },
  "services": {
    "ecommerce": { "status": "PASS", "pass_rate": 88.2 },
    "inventory": { "status": "FAIL", "pass_rate": 41.0 }
  },
  "gate_violations": ["inventory: 41.0% < 80.0% threshold"],
  "allure_report_url": "https://allure.example.com/run/uuid",
  "qmetry_run_id": "QM-1234"
}
```

---

## 9. CI/CD Integration

### 9.1 GitLab Integration

**Option A — Webhook (push-based):**
GitLab sends a webhook to the AITA service on pipeline events. AITA runs and the CI stage waits by polling `GET /runs/{run_id}`.

**Option B — GitLab CI Job (pull-based):**
Add to `.gitlab-ci.yml`:

```yaml
integration-tests:
  stage: test
  image: python:3.12
  script:
    - pip install aita-client
    - aita run
        --service $CI_PROJECT_NAME
        --branch $CI_COMMIT_REF_NAME
        --target $SERVICE_URL
        --watch
        --fail-on-gate-fail
  variables:
    AITA_SERVER: https://aita.internal.example.com
    AITA_API_KEY: $AITA_API_KEY
  artifacts:
    when: always
    reports:
      junit: aita-results/junit.xml
    paths:
      - aita-results/
```

### 9.2 Jenkins Integration

```groovy
stage('Integration Tests') {
    steps {
        sh '''
            aita run \
              --service ${env.SERVICE_NAME} \
              --branch ${env.GIT_BRANCH} \
              --target ${env.SERVICE_URL} \
              --output-dir aita-results \
              --watch \
              --fail-on-gate-fail
        '''
    }
    post {
        always {
            junit 'aita-results/junit.xml'
            allure includeProperties: false, jdk: '', results: [[path: 'aita-results/allure-results']]
        }
    }
}
```

### 9.3 Docker Desktop Support (Requirement #3)

The `DockerAdapter` detects services running in Docker Desktop:

```python
class DockerAdapter(ContainerPort):
    def detect_service(self, service_name: str) -> ServiceTarget | None:
        # Scans running containers, matches by image name or label
        # Returns host:port mapping
        ...

    def is_healthy(self, target: ServiceTarget) -> bool:
        # HTTP health check or Docker health status
        ...
```

CLI usage:
```
aita run --service ecommerce --target docker://ecommerce-service
aita run --service ecommerce --target docker-compose://./docker-compose.yml:ecommerce
```

The adapter reads `docker.sock` via the Docker SDK and resolves port mappings automatically.

---

## 10. Healer Design

The healer is a **multi-stage pipeline** itself, applying progressively more expensive repair strategies.

### 10.1 Healer Stages

```
Stage 1: Static Analysis (no LLM cost)
  - AST parse (Python) or javac compile check (Java)
  - Detect: SyntaxError, IndentationError, unclosed strings,
            Python code inside Java class, missing closing braces,
            truncated method bodies (no closing brace)
  - Action: drop offending block, log warning

Stage 2: Rule-Based Repair (no LLM cost)
  - Pattern: self.api_client → fixture parameter
  - Pattern: self.tdm.X → tdm.X
  - Pattern: assert status_code == 400 when spec says 422
  - Pattern: wrong import path
  - Pattern: Java String literal not closed before EOL
  - Pattern: Python `def test` without `(` on same line
  - Action: regex/AST transform, fix in place

Stage 3: Cross-Language Contamination Check (no LLM cost)
  - CRITICAL: Detect Python `def test_X(self` inside Java class body
  - CRITICAL: Detect Java `void testX()` inside Python file
  - Action: reject entire contaminated block, do NOT attempt repair

Stage 4: Semantic Validation (no LLM cost)
  - Verify: every test method has at least one assertion
  - Verify: every API call has a corresponding assertion on status code
  - Verify: no hardcoded production URLs
  - Action: flag for LLM repair if fixable, else drop

Stage 5: LLM Repair (LLM cost — only if stages 1-4 failed)
  - Send broken test + error messages + spec context to LLM
  - Request targeted fix only (not full regen)
  - Apply returned fix, re-validate with stage 1 and 2
  - If still broken after 2 LLM repair attempts: drop test, store failure pattern
```

### 10.2 Cross-Language Contamination (Requirement #12)

This is explicitly handled as a top-priority check:

```python
def detect_language_contamination(source: str, expected_language: Language) -> list[ContaminationError]:
    errors = []
    if expected_language == Language.JAVA:
        # Python patterns in Java
        python_indicators = [
            r'^\s+def test\w+\s*\(self',
            r'^\s+import pytest',
            r'^\s+@pytest\.',
            r'^\s+assert \w+ ==',     # bare assert (Python style)
        ]
        for pattern in python_indicators:
            if re.search(pattern, source, re.MULTILINE):
                errors.append(ContaminationError(
                    kind="PYTHON_IN_JAVA",
                    pattern=pattern,
                    severity=Severity.CRITICAL,
                ))
    elif expected_language == Language.PYTHON:
        java_indicators = [
            r'\bvoid\s+test\w+\s*\(',
            r'@Test\b',
            r'given\(\)\.contentType\(',
            r'import io\.restassured',
        ]
        ...
    return errors
```

Contamination detection runs **before** any assembly into a file. A contaminated block is **always dropped**, never repaired, and a warning is emitted with the offending line numbers.

### 10.3 Healer Registry

All healer rules are registered in a `HealerRegistry`, making them easy to add, disable, or reorder:

```python
class HealerRegistry:
    def register(self, rule: HealerRule, priority: int) -> None: ...
    def get_rules(self, language: Language) -> list[HealerRule]: ...
    def disable(self, rule_name: str) -> None: ...
```

This means new healer rules (found from production failures) are added as new classes, not as edits to existing code (**Open/Closed Principle**).

---

## 11. Test Repository Strategy

### 11.1 Storage Architecture

```
PostgreSQL (metadata):
  test_cases table — test name, operation_id, status, pass rates, fingerprint

Git bare repository (source):
  One repo per monitored service:
    /test-repo/ecommerce.git
    /test-repo/inventory.git

  Branch strategy:
    main       — latest passing tests
    generated  — freshly generated (pre-validation)
    run/{id}   — snapshot of tests used in a specific run
```

### 11.2 Test Lifecycle

```
1. LLM generates test → saved to `generated` branch + DB (status=DRAFT)
2. Healer validates    → DRAFT → ACTIVE or REJECTED
3. Execution runs      → ACTIVE test, results stored
4. Pass rate tracked   → if pass_rate_7d < 20% and not a real service bug:
                          mark DEPRECATED, open feedback item
5. QE marks feedback   → DEPRECATED → triggers regen with new context
```

### 11.3 Test Reuse

On every run, for **unchanged** endpoints (fingerprint match):
1. Load `ACTIVE` tests from DB for that `operation_id`
2. Checkout from git repo at the stored commit
3. Use directly — **no LLM call**

This is the primary token-saving mechanism.

---

## 12. Reporting & Test Management

### 12.1 Allure Integration (Requirement #18)

Tests are annotated at generation time with Allure decorators/annotations:

**Python:**
```python
@allure.feature("Customers")
@allure.story("Create Customer")
@allure.severity(allure.severity_level.CRITICAL)
def test_create_customer_success(api_client):
    ...
```

**Java:**
```java
@Feature("Warehouses")
@Story("Create Warehouse")
@Severity(SeverityLevel.CRITICAL)
@Test
void testCreateWarehouseSuccess() { ... }
```

After execution, the `ReportStep` pushes results to **Allure TestOps**:

```python
class AllureAdapter(ReportingPort):
    def push_results(self, run: PipelineRun, results_dir: Path) -> str:
        # POST multipart to Allure TestOps REST API
        # Returns URL to the generated report
        ...
```

Configuration:
```yaml
allure:
  server_url: https://allure.internal.example.com
  api_token: ${ALLURE_TOKEN}
  project_id: my-project
  launch_name_template: "AITA: {service} @ {branch}"
```

### 12.2 QMetry Integration (Requirement #20)

```python
class QMetryAdapter(TestManagementPort):
    def sync_test_cases(self, tests: list[TestCase]) -> None:
        # Create or update test cases in QMetry via REST API
        ...

    def push_results(self, run: PipelineRun, results: TestSummary) -> str:
        # Create a test run in QMetry and push results
        ...
```

QMetry test case ID is stored in the `test_cases` table as `external_id` once synced. Re-runs update the same QMetry test case rather than creating duplicates.

**MCP option**: if a QMetry MCP connector is available, the adapter uses it instead of the REST API — configured via `qmetry.adapter: MCP | REST`.

---

## 13. Deployment & Setup

### 13.1 System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| CPU | 4 cores | 8 cores |
| RAM | 8 GB | 16 GB |
| Disk | 20 GB | 100 GB |
| Docker Desktop | 4.x | latest |
| Python | 3.12 | 3.12 |
| Java | 17 | 21 |

### 13.2 Docker Compose Stack

All infrastructure services packaged:

```yaml
# docker-compose.yml
services:
  aita-api:        # FastAPI service
  aita-worker:     # Celery worker(s)
  aita-redis:      # Redis 7
  aita-postgres:   # PostgreSQL 16
  aita-qdrant:     # Qdrant vector store
  aita-ollama:     # Ollama (optional, for on-prem LLM)
  aita-allure:     # Allure server (optional, if not using cloud)
```

### 13.3 Mac Setup Script (`setup-mac.sh`)

```bash
#!/bin/bash
set -e

echo "=== AITA Setup for macOS ==="

# Check Homebrew
if ! command -v brew &>/dev/null; then
  echo "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# Install dependencies
brew install python@3.12 java@17 maven git docker

# Install Python deps
pip3.12 install aita-agent

# Pull Docker images
docker compose pull

# Copy env template
cp .env.example .env
echo "Please edit .env with your API keys"

# Start infrastructure
docker compose up -d aita-redis aita-postgres aita-qdrant

# Run DB migrations
aita db migrate

# Interactive setup
aita setup

echo "=== Setup complete. Run 'aita run --help' to get started ==="
```

### 13.4 Windows Setup Script (`setup-windows.ps1`)

```powershell
# setup-windows.ps1
Write-Host "=== AITA Setup for Windows ===" -ForegroundColor Cyan

# Check winget
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Error "winget not found. Install App Installer from Microsoft Store."
    exit 1
}

# Install dependencies
winget install --id Python.Python.3.12 -e
winget install --id Git.Git -e
winget install --id Microsoft.OpenJDK.17 -e
winget install --id Apache.Maven -e

# Refresh PATH
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine")

# Install Python deps
pip install aita-agent

# Docker check
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker Desktop not found. Please install from https://www.docker.com/products/docker-desktop/"
    Start-Process "https://www.docker.com/products/docker-desktop/"
    Read-Host "Press Enter once Docker Desktop is installed and running"
}

# Pull and start
docker compose pull
Copy-Item .env.example .env
Write-Host "Please edit .env with your API keys" -ForegroundColor Yellow
docker compose up -d aita-redis aita-postgres aita-qdrant

# Run setup wizard
aita db migrate
aita setup

Write-Host "=== Setup complete ===" -ForegroundColor Green
```

### 13.5 Environment Variables

```bash
# .env.example

# LLM
ANTHROPIC_API_KEY=sk-ant-...
OLLAMA_BASE_URL=http://localhost:11434      # for on-prem LLM
LLM_PROVIDER=anthropic                     # anthropic | ollama | openai

# Infrastructure
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql://aita:aita@localhost:5432/aita
QDRANT_URL=http://localhost:6333

# Git
GIT_TOKEN=ghp_...                          # GitHub/GitLab PAT
GIT_SSH_KEY_PATH=~/.ssh/id_rsa             # alternative to token

# Reporting
ALLURE_SERVER_URL=https://allure.example.com
ALLURE_API_TOKEN=...
ALLURE_PROJECT_ID=my-project

# Test Management
QMETRY_URL=https://testmanagement.example.com
QMETRY_API_KEY=...
QMETRY_PROJECT_KEY=PROJ

# API
AITA_API_KEY=...                           # auth token for AITA REST API
AITA_SERVER_URL=http://localhost:8000      # for CLI client connecting to remote server
```

---

## 14. Design Patterns Applied

| Pattern | Where Used | Why |
|---|---|---|
| **Hexagonal / Ports & Adapters** | Overall architecture | Decouple core logic from infrastructure, swap adapters without touching business logic |
| **Template Method** | `PipelineOrchestrator` | Fixed pipeline skeleton, pluggable steps |
| **Strategy** | `SpecParser`, `SourceScanner`, `LLMAdapter` | Swap parsers/scanners/providers without changing core |
| **Chain of Responsibility** | Healer stages | Each stage handles what it can, passes remainder to next |
| **Registry** | `HealerRegistry`, `ParserRegistry` | Open for extension, closed for modification |
| **Observer / Event Bus** | Progress streaming | Steps emit events; CLI/SSE/logs consume independently |
| **Facade** | `AITAClient` (Python SDK) | Single entry point for CLI and CI adapter |
| **Repository** | `TestCaseRepository`, `FeedbackRepository` | Decouple DB access from business logic |
| **Factory** | `AdapterFactory` | Create correct adapter based on config without if/else everywhere |
| **Circuit Breaker** | LLM calls, Git operations | Fail fast if LLM/Git is down, don't block the pipeline indefinitely |
| **Bulkhead** | Celery worker pools | Separate pools for generation (LLM-heavy) and execution (I/O-heavy) |
| **Saga** | Pipeline run recovery | Each step records state; failed runs can be resumed from last checkpoint |

---

## 15. Phase-by-Phase Delivery Plan

### Phase 0 — Foundation (Weeks 1–2)

**Goal:** Skeleton project, infrastructure up, nothing works yet but the bones are right.

- [ ] Set up Python project structure (Hexagonal, typed)
- [ ] Docker Compose with Redis, PostgreSQL, Qdrant
- [ ] FastAPI application skeleton with health endpoint
- [ ] Celery worker skeleton
- [ ] DB schema and migrations (Alembic)
- [ ] Adapter interfaces (ports) defined — no implementations yet
- [ ] Configuration management (`pydantic-settings`)
- [ ] Logging setup (structured JSON logs)
- [ ] CI for the AITA project itself (lint, type-check, unit tests)
- [ ] Basic CLI skeleton (`aita --help`)

**Deliverable:** `docker compose up` starts all services; `aita --help` works.

---

### Phase 1 — Spec Parsing & Source Scanning (Weeks 3–4)

**Goal:** Read any service's specification and understand its structure.

- [ ] `GitAdapter` — clone, fetch, branch checkout
- [ ] `OpenApiParser` — parse OpenAPI 3.x YAML/JSON into `ServiceSpec`
- [ ] `SwaggerParser` — parse Swagger 2.x
- [ ] `ProtoParser` — parse `.proto` files
- [ ] Auto-detect spec file in repo
- [ ] `SourceScanner` for Spring Boot (annotations, validators)
- [ ] `SourceScanner` for FastAPI (Depends, Pydantic)
- [ ] Unit tests for all parsers
- [ ] Graceful error handling: spec not found, invalid spec, Git auth failure

**Deliverable:** `aita services add --repo-url X --branch Y` detects and parses spec.

---

### Phase 2 — Caching & Fingerprinting (Week 5)

**Goal:** Intelligent change detection, never regenerate what hasn't changed.

- [ ] `RedisAdapter` implementation
- [ ] `EndpointFingerprinter` — semantic hash per endpoint
- [ ] Fingerprint storage and retrieval
- [ ] Diff logic: changed / unchanged / new / deleted endpoints
- [ ] `aita cache` CLI commands
- [ ] `TestCaseRepository` — PostgreSQL + Git bare repo
- [ ] Test reuse path: load from repo for unchanged endpoints

**Deliverable:** Running twice with no spec change → zero LLM calls.

---

### Phase 3 — Test Generation (Weeks 6–8)

**Goal:** Generate working tests for any REST or gRPC service.

- [ ] `AnthropicAdapter` LLM implementation
- [ ] `OllamaAdapter` LLM implementation (on-prem fallback)
- [ ] `PromptBuilder` — construct enriched generation prompts
- [ ] `TestGenerator` — parallel per-endpoint generation
- [ ] LLM response cache (Level 2)
- [ ] Python pytest test assembler
- [ ] Java JUnit 5 + REST-assured test assembler
- [ ] Test file persistence to Git repo + DB
- [ ] Token usage tracking and logging
- [ ] Semaphore-limited concurrency

**Deliverable:** `aita generate --service ecommerce` produces runnable test files.

---

### Phase 4 — Healer (Week 9)

**Goal:** No broken test ever reaches execution.

- [ ] `HealerRegistry` and `HealerRule` base class
- [ ] Stage 1: AST parse (Python) + javac compile check (Java)
- [ ] Stage 2: All rule-based fixers (self-fixture, import paths, etc.)
- [ ] Stage 3: Cross-language contamination detection
- [ ] Stage 4: Semantic validation (missing assertions, etc.)
- [ ] Stage 5: LLM repair (with 2-attempt limit)
- [ ] Healer result logging and feedback creation for dropped tests
- [ ] Unit tests: each healer rule has a passing and failing test case

**Deliverable:** Feed the healer known-broken tests from the PoC; all are caught and handled.

---

### Phase 5 — Execution & Results (Week 10)

**Goal:** Run tests against live or Docker services, collect structured results.

- [ ] `DockerAdapter` — detect running containers, resolve ports
- [ ] `TestExecutor` for pytest (subprocess with JSON report)
- [ ] `TestExecutor` for Maven/JUnit (subprocess, parse surefire XML)
- [ ] `ServiceCallLogger` — structured request/response logging
- [ ] Real-time progress streaming (SSE)
- [ ] `TestSummary` construction
- [ ] Quality gate evaluator

**Deliverable:** `aita run --service ecommerce --target docker://ecommerce` runs full pipeline end-to-end.

---

### Phase 6 — Learning & Feedback (Weeks 11–12)

**Goal:** Every run makes the next run smarter.

- [ ] `FeedbackCollector` — auto-generate feedback from failures
- [ ] `PatternLearner` — extract patterns from pass/fail history
- [ ] `FeedbackRepository` (PostgreSQL)
- [ ] YAML feedback import (`aita feedback --import`)
- [ ] Feedback injection into generation prompt
- [ ] Anti-pattern exclusion from prompts
- [ ] `aita feedback --list`, `--mark-applied`

**Deliverable:** Import QE feedback YAML; next run generates tests targeting the feedback scenarios.

---

### Phase 7 — RAG Knowledge Base (Weeks 13–14)

**Goal:** Tests informed by domain knowledge, not just the spec.

- [ ] `QdrantAdapter` — vector store integration
- [ ] `DocumentIngester` — PDF, Markdown, text
- [ ] Naive RAG: embed + search similar chunks
- [ ] Graph RAG: Neo4j entity relationships (optional, flag-gated)
- [ ] Agentic RAG: LlamaIndex agent with retrieval tools
- [ ] Fusion ranker (RRF)
- [ ] `aita learn` CLI command
- [ ] Confluence ingester (REST API)

**Deliverable:** `aita learn --from docs/` enriches future test generation with domain knowledge.

---

### Phase 8 — CI/CD Integration (Week 15)

**Goal:** Drop-in integration with GitLab and Jenkins.

- [ ] GitLab webhook receiver
- [ ] Jenkins webhook receiver
- [ ] `aita run --watch` CI-friendly output (structured logs)
- [ ] JUnit XML output for CI artifact
- [ ] `--fail-on-gate-fail` exit code
- [ ] GitLab `.gitlab-ci.yml` example
- [ ] Jenkins `Jenkinsfile` example
- [ ] CI authentication (API key header)

**Deliverable:** `.gitlab-ci.yml` with AITA job runs integration tests on every push.

---

### Phase 9 — Reporting & Test Management (Week 16)

**Goal:** Results visible in Allure and QMetry.

- [ ] `AllureAdapter` — push results to Allure TestOps
- [ ] Allure annotations injected at generation time
- [ ] `QMetryAdapter` (REST) — sync test cases and results
- [ ] QMetry MCP option (if MCP server available)
- [ ] `aita status` — display last run with Allure URL

**Deliverable:** Every run pushes results to Allure server and syncs to QMetry.

---

### Phase 10 — CLI Polish & Setup (Week 17)

**Goal:** Any engineer can install and use this in one session.

- [ ] Rich progress panel in CLI
- [ ] `aita setup` interactive wizard
- [ ] `setup-mac.sh` tested on macOS 14+
- [ ] `setup-windows.ps1` tested on Windows 11
- [ ] `aita doctor` — check all dependencies and connectivity
- [ ] Comprehensive error messages with remediation hints
- [ ] Full README and setup guide

**Deliverable:** A new engineer installs and runs their first pipeline in under 30 minutes.

---

### Phase 11 — Hardening (Week 18)

**Goal:** Production-ready reliability.

- [ ] Circuit breakers on all external calls
- [ ] Retry with exponential backoff (LLM, Git, Allure, QMetry)
- [ ] Saga pattern: pipeline run checkpointing and resumption
- [ ] Comprehensive integration test suite for AITA itself
- [ ] Load test: 5 services × 20 endpoints in parallel
- [ ] Memory and resource profiling
- [ ] Security: API key rotation, secrets via env only

---

### Future Phases (Post-MVP)

- **LangGraph migration**: replace `PipelineOrchestrator` with a LangGraph state machine — the Hexagonal architecture means this is a swap of the orchestration layer only
- **Haystack pipeline**: wrap document ingestion in a Haystack pipeline for richer pre-processing
- **Neo4j Graph RAG**: full relationship graph across all services' entities
- **GraphQL support**: `GraphQLParser` and test generator strategy
- **Web dashboard**: React frontend consuming the SSE and REST APIs

---

## 16. Open Questions & Decisions

| # | Question | Options | Decision | Owner |
|---|---|---|---|---|
| 1 | Test file storage: Git bare repo vs S3 vs DB blob | Git / S3 / DB | Git (version history is valuable) | TBD |
| 2 | Embedding model: OpenAI vs Ollama local | OpenAI / Ollama | Configurable, default Ollama (on-prem) | TBD |
| 3 | Graph RAG (Neo4j): required or optional? | Required / Optional / Skip | Optional (flag-gated, Phase 7+) | TBD |
| 4 | QMetry integration: REST API vs MCP | REST / MCP | REST first, MCP if available | TBD |
| 5 | Java test compilation check: in-process javac vs subprocess | In-process / subprocess | Subprocess (avoids classpath complexity) | TBD |
| 6 | Multi-tenancy: single team or multi-tenant SaaS? | Single / Multi | Single team for v1 | TBD |
| 7 | Allure: self-hosted vs TestOps cloud? | Self-hosted / Cloud | Configurable URL, customer decides | TBD |
| 8 | Authentication for AITA API: API key vs OAuth2? | API key / OAuth2 | API key for v1, OAuth2 later | TBD |

---

*End of document. Update this plan before implementing each phase.*
