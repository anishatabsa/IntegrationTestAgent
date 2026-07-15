"""GitPython-backed implementation of GitPort."""
from __future__ import annotations

from pathlib import Path

import structlog
from git import GitCommandError, InvalidGitRepositoryError, Repo
from tenacity import retry, stop_after_attempt, wait_exponential

from aita.domain.exceptions import BranchNotFoundError, GitError
from aita.ports.outbound.git_port import GitPort

logger = structlog.get_logger()


class GitAdapter(GitPort):
    def __init__(self, ssh_key_path: str | None = None) -> None:
        self._env: dict[str, str] = {}
        if ssh_key_path:
            self._env["GIT_SSH_COMMAND"] = f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def clone_or_pull(self, repo_url: str, target_dir: Path, branch: str) -> str:
        try:
            try:
                repo = Repo(str(target_dir))
                logger.info("git_pull", branch=branch)
                origin = repo.remote("origin")
                origin.fetch(env=self._env)
                repo.git.checkout(branch)
                origin.pull(branch, env=self._env)
            except (InvalidGitRepositoryError, ValueError):
                logger.info("git_clone", url=repo_url)
                repo = Repo.clone_from(
                    repo_url,
                    str(target_dir),
                    branch=branch,
                    env=self._env,
                )
        except GitCommandError as exc:
            if "not found" in str(exc) or "pathspec" in str(exc):
                raise BranchNotFoundError(f"Branch '{branch}' not found in {repo_url}") from exc
            raise GitError(f"Git operation failed: {exc}") from exc

        return repo.head.commit.hexsha

    async def checkout(self, repo_dir: Path, ref: str) -> None:
        try:
            repo = Repo(str(repo_dir))
            repo.git.checkout(ref)
        except GitCommandError as exc:
            raise GitError(f"Checkout failed: {exc}") from exc

    async def list_changed_files(self, repo_dir: Path, from_ref: str, to_ref: str) -> list[str]:
        try:
            repo = Repo(str(repo_dir))
            diff = repo.git.diff("--name-only", from_ref, to_ref)
            return [f for f in diff.splitlines() if f]
        except GitCommandError as exc:
            raise GitError(f"Diff failed: {exc}") from exc

    async def commit_and_push(self, repo_dir: Path, message: str, paths: list[Path]) -> str:
        try:
            repo = Repo(str(repo_dir))
            repo.index.add([str(p) for p in paths])
            commit = repo.index.commit(message)
            repo.remote("origin").push(env=self._env)
            return commit.hexsha
        except GitCommandError as exc:
            raise GitError(f"Commit/push failed: {exc}") from exc
