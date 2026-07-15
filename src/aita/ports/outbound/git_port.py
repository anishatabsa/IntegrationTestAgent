"""Outbound port — git operations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class GitPort(ABC):

    @abstractmethod
    async def clone_or_pull(self, repo_url: str, target_dir: Path, branch: str) -> str:
        """Clone repo if missing, else pull. Returns resolved commit SHA."""

    @abstractmethod
    async def checkout(self, repo_dir: Path, ref: str) -> None:
        """Checkout a branch / tag / commit in an existing clone."""

    @abstractmethod
    async def list_changed_files(self, repo_dir: Path, from_ref: str, to_ref: str) -> list[str]:
        """List files changed between two refs."""

    @abstractmethod
    async def commit_and_push(
        self, repo_dir: Path, message: str, paths: list[Path]
    ) -> str:
        """Stage paths, commit, and push. Returns new commit SHA."""
