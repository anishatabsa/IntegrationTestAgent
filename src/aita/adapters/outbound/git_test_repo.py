"""Git-backed test repository adapter — one bare repo per service."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

import structlog

from aita.domain.models import TestCase
from aita.ports.outbound.git_port import GitPort
from aita.ports.outbound.test_repo_port import TestRepoPort

logger = structlog.get_logger()


class GitTestRepoAdapter(TestRepoPort):
    """
    Stores generated test files in a local bare git repo per service.
    Directory layout: <base_path>/<service_name>/<operation_id>.<ext>
    """

    def __init__(self, base_path: Path, git_port: GitPort) -> None:
        self._base = base_path
        self._git = git_port

    def _service_dir(self, service_name: str) -> Path:
        d = self._base / service_name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _file_path(self, service_name: str, operation_id: str, language: str) -> Path:
        ext = "java" if language == "java" else "py"
        return self._service_dir(service_name) / f"test_{operation_id}.{ext}"

    async def load(self, service_name: str, operation_id: str) -> TestCase | None:
        for ext, lang in [("py", "python"), ("java", "java")]:
            p = self._service_dir(service_name) / f"test_{operation_id}.{ext}"
            if p.exists():
                from aita.domain.enums import Language, TestStatus
                return TestCase(
                    endpoint_id=UUID(int=0),
                    name=f"test_{operation_id}",
                    content=p.read_text(encoding="utf-8"),
                    language=Language(lang),
                    status=TestStatus.GENERATED,
                )
        return None

    async def save(self, service_name: str, test_case: TestCase) -> str:
        op_id = test_case.name.removeprefix("test_")
        file_path = self._file_path(service_name, op_id, test_case.language.value)
        file_path.write_text(test_case.content, encoding="utf-8")

        # Commit to local git repo
        try:
            service_dir = self._service_dir(service_name)
            # Init git repo if needed
            from git import Repo, InvalidGitRepositoryError
            try:
                repo = Repo(str(service_dir))
            except InvalidGitRepositoryError:
                repo = Repo.init(str(service_dir))

            repo.index.add([str(file_path.name)])
            if repo.is_dirty(index=True):
                commit = repo.index.commit(f"chore: update {file_path.name}")
                return commit.hexsha
            return repo.head.commit.hexsha if repo.head.is_valid() else "initial"
        except Exception as exc:
            logger.warning("test_repo_commit_failed", error=str(exc))
            return "no-git"

    async def delete(self, service_name: str, operation_id: str) -> None:
        for ext in ["py", "java"]:
            p = self._service_dir(service_name) / f"test_{operation_id}.{ext}"
            if p.exists():
                p.unlink()

    async def list_operations(self, service_name: str) -> list[str]:
        d = self._service_dir(service_name)
        ops: list[str] = []
        for f in d.glob("test_*.*"):
            stem = f.stem  # test_<operation_id>
            ops.append(stem.removeprefix("test_"))
        return ops
