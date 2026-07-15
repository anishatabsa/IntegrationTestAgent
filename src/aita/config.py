"""Application configuration via pydantic-settings (reads from .env)."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Application ────────────────────────────────────────────────────────────
    app_env: str = "development"
    app_log_level: str = "INFO"
    app_secret_key: str = "change-me"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://aita:aita_secret@localhost:5432/aita"
    database_pool_size: int = 10

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_llm_cache_ttl: int = 86400

    # ── Celery ────────────────────────────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "codellama:13b"
    llm_max_tokens: int = 8192
    llm_temperature: float = 0.2

    # ── Vector Store ──────────────────────────────────────────────────────────
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "aita_knowledge"

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    neo4j_enabled: bool = False
    neo4j_url: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # ── Git ───────────────────────────────────────────────────────────────────
    git_default_branch: str = "main"
    git_ssh_key_path: str = ""
    gitlab_token: str = ""
    github_token: str = ""

    # ── Test Repository ───────────────────────────────────────────────────────
    test_repo_base_path: Path = Path("./test-repos")

    # ── Docker ────────────────────────────────────────────────────────────────
    docker_target_network: str = "bridge"
    docker_socket: str = "unix:///var/run/docker.sock"

    # ── Allure ────────────────────────────────────────────────────────────────
    allure_server_url: str = "http://localhost:5050"
    allure_project_id: str = "aita"
    allure_api_token: str = ""

    # ── QMetry ────────────────────────────────────────────────────────────────
    qmetry_enabled: bool = False
    qmetry_base_url: str = ""
    qmetry_api_key: str = ""
    qmetry_project_key: str = ""

    # ── CI ─────────────────────────────────────────────────────────────────────
    ci_webhook_secret: str = "change-me"

    # ── Quality Gate ──────────────────────────────────────────────────────────
    quality_gate_threshold: float = 80.0


settings = Settings()
