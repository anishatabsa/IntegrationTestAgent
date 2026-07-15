"""Outbound port — Docker Desktop interaction."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ContainerInfo:
    container_id: str
    name: str
    image: str
    status: str
    ports: dict[int, int]   # container_port → host_port
    labels: dict[str, str]


class DockerPort(ABC):

    @abstractmethod
    async def find_container(self, service_name: str) -> ContainerInfo | None:
        """Find a running container by name or label."""

    @abstractmethod
    async def get_base_url(self, container: ContainerInfo, container_port: int = 8080) -> str:
        """Return the host-accessible base URL for a container port."""

    @abstractmethod
    async def health_check(self, base_url: str, path: str = "/health") -> bool:
        """Return True if the service responds on the health path."""

    @abstractmethod
    async def list_containers(self) -> list[ContainerInfo]:
        """List all running containers."""
