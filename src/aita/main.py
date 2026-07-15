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
    async def embedder(texts: list[str]) -> list[list[float]]:
        # Default: use Ollama nomic-embed-text or a simple placeholder
        import ollama as _ollama
        results = []
        for text in texts:
            resp = _ollama.embeddings(model="nomic-embed-text", prompt=text)
            results.append(resp["embedding"])
        return results

    vector_store = QdrantAdapter(qdrant_client, embedder)
    await vector_store.ensure_collection(settings.qdrant_collection, vector_size=768)

    # ── RAG ──────────────────────────────────────────────────────────────────
    naive_rag = NaiveRAG(vector_store, settings.qdrant_collection)
    agentic_rag = AgenticRAG(vector_store, settings.qdrant_collection)
    rag_engine = RAGEngine(naive_rag, agentic_rag)

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

    # ── Git-backed test repo (placeholder — wire in full impl) ─────────────
    from aita.adapters.outbound.git_test_repo import GitTestRepoAdapter
    test_repo = GitTestRepoAdapter(settings.test_repo_base_path, git_adapter)

    # ── Pipeline steps ────────────────────────────────────────────────────────
    steps = [
        GitPullStep(git_adapter, settings.test_repo_base_path),
        SpecParseStep(spec_registry),
        SourceScanStep(scanner_registry),
        EndpointDiffStep(fingerprinter, cache),
        RAGEnrichStep(rag_engine),
        GenerateStep(generator),
        HealStep(healer),
        PersistStep(test_repo),
        ExecuteStep(executor, docker),
        FeedbackStep(FeedbackCollector(), PatternLearner()),
        ReportStep(allure, qmetry, allure_results_dir),
        GateStep(settings.quality_gate_threshold),
    ]

    app.state.orchestrator = PipelineOrchestrator(steps, cache)
    app.state.ingester = KnowledgeIngester(vector_store, settings.qdrant_collection)

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
