"""FastAPI application factory and lifespan."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from redis.asyncio import Redis

from aita.adapters.inbound.rest.routers import knowledge, runs, services, webhooks
from aita.adapters.outbound.allure_adapter import AllureAdapter
from aita.adapters.outbound.anthropic_adapter import AnthropicAdapter
from aita.adapters.outbound.docker_adapter import DockerAdapter
from aita.adapters.outbound.git_adapter import GitAdapter
from aita.adapters.outbound.ollama_adapter import OllamaAdapter
from aita.adapters.outbound.qdrant_adapter import QdrantAdapter
from aita.adapters.outbound.qmetry_adapter import QMetryAdapter
from aita.adapters.outbound.redis_adapter import RedisAdapter
from aita.config import settings
from aita.core.executor.maven_executor import MavenExecutor
from aita.core.executor.pytest_executor import PytestExecutor
from aita.core.feedback.collector import FeedbackCollector
from aita.core.feedback.pattern_learner import PatternLearner
from aita.core.feedback.pattern_store import InMemoryPatternStore
from aita.core.fingerprint.fingerprinter import EndpointFingerprinter
from aita.core.generator.test_generator import TestGenerator
from aita.core.healer.healer import HealerPipeline
from aita.core.healer.rules.cross_lang_rule import CrossLangContaminationRule
from aita.core.healer.rules.llm_repair_rule import LLMRepairRule
from aita.core.healer.rules.rule_based_repair_rule import RuleBasedRepairRule
from aita.core.healer.rules.semantic_validation_rule import SemanticValidationRule
from aita.core.healer.rules.static_analysis_rule import StaticAnalysisRule
from aita.core.knowledge.agentic_rag import AgenticRAG
from aita.core.knowledge.ingester import KnowledgeIngester
from aita.core.knowledge.naive_rag import NaiveRAG
from aita.core.knowledge.rag_engine import RAGEngine
from aita.core.orchestrator import PipelineOrchestrator
from aita.core.pipeline.steps.endpoint_diff_step import EndpointDiffStep
from aita.core.pipeline.steps.execute_step import ExecuteStep
from aita.core.pipeline.steps.feedback_step import FeedbackStep
from aita.core.pipeline.steps.gate_step import GateStep
from aita.core.pipeline.steps.publish_step import PublishStep
from aita.core.pipeline.steps.fetch_existing_step import FetchExistingTestsStep
from aita.core.pipeline.steps.generate_step import GenerateStep
from aita.core.pipeline.steps.git_pull_step import GitPullStep
from aita.core.pipeline.steps.heal_step import HealStep
from aita.core.pipeline.steps.persist_step import PersistStep
from aita.core.pipeline.steps.rag_enrich_step import RAGEnrichStep
from aita.core.pipeline.steps.report_step import ReportStep
from aita.core.pipeline.steps.source_scan_step import SourceScanStep
from aita.core.pipeline.steps.spec_parse_step import SpecParseStep
from aita.core.scanner.fastapi_scanner import FastAPIScanner
from aita.core.scanner.source_scanner import SourceScannerRegistry
from aita.core.scanner.spring_boot_scanner import SpringBootScanner
from aita.core.spec.openapi_parser import OpenAPIParser
from aita.core.spec.parser import SpecParserRegistry
from aita.core.spec.proto_parser import ProtoParser
from aita.core.spec.swagger_parser import SwaggerParser
from aita.shared.logging import configure_logging

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.app_log_level)
    logger.info("aita_starting", env=settings.app_env)

    # ── Infrastructure ────────────────────────────────────────────────────────
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    cache = RedisAdapter(redis_client)

    from qdrant_client import AsyncQdrantClient
    qdrant_client = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)

    # ── LLM adapter ──────────────────────────────────────────────────────────
    if settings.llm_provider == "anthropic":
        llm = AnthropicAdapter(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            cache=cache,
            cache_ttl=settings.redis_llm_cache_ttl,
        )
    else:
        llm = OllamaAdapter(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            cache=cache,
            cache_ttl=settings.redis_llm_cache_ttl,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )

    # ── Vector store + embedder ────────────────────────────────────────────────
    # Embedder: Ollama nomic-embed-text (768-dim).
    # Uses the batch embed() API (ollama SDK >=0.3 / Ollama server >=0.1.33).
    # Falls back to the legacy embeddings() API for older SDK installs.
    # The sync Ollama client uses `requests` — dispatched via asyncio.to_thread()
    # so it never blocks the event loop.
    _ollama_model = settings.ollama_model if settings.llm_provider == "ollama" else "nomic-embed-text"

    def _embed_sync(texts: list[str]) -> list[list[float]]:
        import ollama as _ollama
        client = _ollama.Client(host=settings.ollama_base_url)
        try:
            # Preferred: batch embed() API (ollama SDK >=0.3, server >=0.1.33)
            # POST /api/embed  —  returns EmbedResponse with .embeddings: list[list[float]]
            resp = client.embed(model=_ollama_model, input=texts)
            embeddings = resp.embeddings if hasattr(resp, "embeddings") else resp["embeddings"]
            return [list(e) for e in embeddings]
        except (AttributeError, KeyError, TypeError):
            pass
        # Fallback: legacy per-text embeddings() API (ollama SDK <0.3)
        # POST /api/embeddings  —  returns {"embedding": list[float]}
        results = []
        for text in texts:
            resp = client.embeddings(model=_ollama_model, prompt=text)
            emb = resp["embedding"] if isinstance(resp, dict) else resp.embedding
            results.append(list(emb))
        return results

    async def embedder(texts: list[str]) -> list[list[float]]:
        import asyncio
        return await asyncio.to_thread(_embed_sync, texts)

    # ── Embedder startup: ensure model is available ───────────────────────────
    import asyncio as _asyncio
    try:
        # Auto-pull nomic-embed-text if not present (runs synchronously at boot).
        import ollama as _ollama_boot
        _boot_client = _ollama_boot.Client(host=settings.ollama_base_url)
        try:
            _model_list = _boot_client.list()
            _available = [
                m.model if hasattr(m, "model") else m.get("model", "")
                for m in (_model_list.models if hasattr(_model_list, "models") else _model_list.get("models", []))
            ]
            if not any(_ollama_model in m for m in _available):
                logger.info("pulling_embedding_model", model=_ollama_model)
                _boot_client.pull(model=_ollama_model)
                logger.info("embedding_model_pulled", model=_ollama_model)
        except Exception as _list_err:
            logger.warning("embedding_model_list_failed", error=str(_list_err))

        # Health check: embed one string and confirm we get a 768-dim vector back.
        _test_vecs = await _asyncio.to_thread(_embed_sync, ["aita embedder health check"])
        _dim = len(_test_vecs[0])
        logger.info("embedder_healthy", model=_ollama_model, dim=_dim)
        if _dim != 768:
            logger.warning(
                "embedder_dimension_mismatch",
                expected=768,
                got=_dim,
                hint="Qdrant collection was created with vector_size=768. "
                     "Re-ingest after changing embedding models.",
            )
    except Exception as _health_err:
        logger.error(
            "embedder_unhealthy",
            error=str(_health_err),
            error_type=type(_health_err).__name__,
            hint=(
                "RAG will return 0 snippets until this is fixed. "
                f"Ensure Ollama is running and '{_ollama_model}' is pulled. "
                "Run: docker exec integrationtestagent-aita-ollama-1 "
                f"ollama pull {_ollama_model}"
            ),
        )

    vector_store = QdrantAdapter(qdrant_client, embedder)

    # Retry ensure_collection — Qdrant may still be booting when the API starts.
    from tenacity import retry, stop_after_delay, wait_fixed, retry_if_exception_type
    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_fixed(2),
        stop=stop_after_delay(30),
        reraise=True,
    )
    async def _ensure_collection_with_retry() -> None:
        await vector_store.ensure_collection(settings.qdrant_collection, vector_size=768)

    try:
        await _ensure_collection_with_retry()
    except Exception as _qdrant_err:
        logger.error(
            "qdrant_unavailable",
            error=str(_qdrant_err),
            hint="Qdrant did not become ready within 30 s. "
                 "Check: docker-compose up -d aita-qdrant",
        )
        raise

    # ── RAG + pattern store ───────────────────────────────────────────────────
    naive_rag = NaiveRAG(vector_store, settings.qdrant_collection)
    agentic_rag = AgenticRAG(vector_store, settings.qdrant_collection)
    # Shared in-memory store: FeedbackStep writes into it after each run,
    # RAGEngine reads from it on the next run so the LLM sees past failures.
    pattern_store = InMemoryPatternStore()
    rag_engine = RAGEngine(
        naive_rag,
        agentic_rag,
        pattern_store=pattern_store.get_patterns,
        feedback_store=pattern_store.get_feedback,
    )

    # ── Spec parsers ──────────────────────────────────────────────────────────
    spec_registry = SpecParserRegistry([OpenAPIParser(), SwaggerParser(), ProtoParser()])

    # ── Source scanners ───────────────────────────────────────────────────────
    scanner_registry = SourceScannerRegistry([SpringBootScanner(), FastAPIScanner()])

    # ── Fingerprinter ─────────────────────────────────────────────────────────
    fingerprinter = EndpointFingerprinter()

    # ── Generator ─────────────────────────────────────────────────────────────
    generator = TestGenerator(llm)

    # ── Healer (5 stages) ─────────────────────────────────────────────────────
    healer = HealerPipeline([
        StaticAnalysisRule(),
        RuleBasedRepairRule(),
        CrossLangContaminationRule(),
        SemanticValidationRule(),
        LLMRepairRule(llm),
    ])

    # ── Executor ──────────────────────────────────────────────────────────────
    allure_results_dir = Path("/tmp/aita-allure-results")
    allure_results_dir.mkdir(exist_ok=True)
    executor = PytestExecutor(allure_results_dir=allure_results_dir)

    # ── External adapters ─────────────────────────────────────────────────────
    docker = DockerAdapter(settings.docker_socket)
    allure = AllureAdapter(settings.allure_server_url, settings.allure_project_id, settings.allure_api_token)
    qmetry = QMetryAdapter(settings.qmetry_base_url, settings.qmetry_api_key, settings.qmetry_project_key)
    git_adapter = GitAdapter(settings.git_ssh_key_path or None)

    # ── Pipeline steps ────────────────────────────────────────────────────────
    steps = [
        GitPullStep(git_adapter, settings.test_repo_base_path),
        SpecParseStep(spec_registry),
        SourceScanStep(scanner_registry),
        EndpointDiffStep(fingerprinter, cache),
        RAGEnrichStep(rag_engine),
        FetchExistingTestsStep(),
        GenerateStep(generator),
        HealStep(healer),
        PersistStep(),
        ExecuteStep(executor, docker),
        FeedbackStep(FeedbackCollector(), PatternLearner(), pattern_sink=pattern_store),
        ReportStep(allure, qmetry, allure_results_dir),
        GateStep(settings.quality_gate_threshold),
        PublishStep(),
    ]

    app.state.orchestrator = PipelineOrchestrator(steps, cache)
    app.state.ingester = KnowledgeIngester(vector_store, settings.qdrant_collection)
    app.state.rag_engine = rag_engine
    app.state.vector_store = vector_store

    logger.info("aita_started")
    yield

    # ── Cleanup ───────────────────────────────────────────────────────────────
    await redis_client.aclose()
    await qdrant_client.close()
    logger.info("aita_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AITA — AI Integration Test Agent",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(runs.router)
    app.include_router(services.router)
    app.include_router(knowledge.router)
    app.include_router(webhooks.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
