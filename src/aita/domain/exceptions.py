"""Domain exception hierarchy."""


class AITAError(Exception):
    """Base exception for all AITA errors."""


# ── Git ──────────────────────────────────────────────────────────────────────
class GitError(AITAError):
    """Git operation failed (clone, checkout, pull, etc.)."""


class BranchNotFoundError(GitError):
    """Requested branch does not exist in remote."""


# ── Spec ─────────────────────────────────────────────────────────────────────
class SpecNotFoundError(AITAError):
    """No spec file (openapi.yaml / swagger.yaml / .proto) found in repo."""


class SpecParseError(AITAError):
    """Spec file exists but could not be parsed."""


# ── Docker ───────────────────────────────────────────────────────────────────
class DockerError(AITAError):
    """Docker Desktop not running or container not found."""


class ServiceNotReachableError(DockerError):
    """Target service container is running but not reachable on expected port."""


# ── LLM ──────────────────────────────────────────────────────────────────────
class LLMError(AITAError):
    """LLM call failed (rate-limit, timeout, auth, etc.)."""


class LLMRepairExhaustedError(LLMError):
    """Healer exceeded max LLM repair attempts without success."""


# ── Healer ───────────────────────────────────────────────────────────────────
class HealerError(AITAError):
    """Healer pipeline failed to produce valid test code."""


class CrossLangContaminationError(HealerError):
    """Generated code contains fragments from a different language."""


# ── Cache ─────────────────────────────────────────────────────────────────────
class CacheError(AITAError):
    """Cache read / write failed."""


# ── Executor ─────────────────────────────────────────────────────────────────
class ExecutorError(AITAError):
    """Test execution failed to start or complete."""


# ── Reporting ────────────────────────────────────────────────────────────────
class AllureError(AITAError):
    """Allure server communication error."""


class QMetryError(AITAError):
    """QMetry API communication error."""


# ── Pipeline ─────────────────────────────────────────────────────────────────
class PipelineStepError(AITAError):
    """A pipeline step failed; wraps the original cause."""
    def __init__(self, step: str, message: str, cause: Exception | None = None):
        super().__init__(f"[{step}] {message}")
        self.step = step
        self.cause = cause
