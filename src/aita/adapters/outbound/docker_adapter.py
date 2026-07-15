"""Docker SDK adapter implementing DockerPort."""
from __future__ import annotations

import structlog
import httpx

from aita.domain.exceptions import DockerError
from aita.ports.outbound.docker_port import ContainerInfo, DockerPort

logger = structlog.get_logger()


class DockerAdapter(DockerPort):
    def __init__(self, socket_url: str = "unix:///var/run/docker.sock") -> None:
        self._socket_url = socket_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import docker
                self._client = docker.DockerClient(base_url=self._socket_url)
            except Exception as exc:
                raise DockerError(f"Cannot connect to Docker: {exc}") from exc
        return self._client

    async def find_container(self, service_name: str) -> ContainerInfo | None:
        try:
            client = self._get_client()
            containers = client.containers.list()
            for c in containers:
                # Match by name or label
                names = [n.lstrip("/") for n in c.attrs.get("Names", [])]
                labels = c.labels or {}
                if service_name in names or labels.get("aita.service") == service_name:
                    return self._to_info(c)
                # Fuzzy: name contains service_name
                if any(service_name in n for n in names):
                    return self._to_info(c)
        except DockerError:
            raise
        except Exception as exc:
            raise DockerError(f"Docker list error: {exc}") from exc
        return None

    def _to_info(self, container) -> ContainerInfo:
        ports: dict[int, int] = {}
        port_bindings = container.attrs.get("HostConfig", {}).get("PortBindings", {}) or {}
        for container_port, bindings in port_bindings.items():
            if bindings:
                cp = int(container_port.split("/")[0])
                hp = int(bindings[0]["HostPort"])
                ports[cp] = hp
        return ContainerInfo(
            container_id=container.short_id,
            name=container.name,
            image=container.image.tags[0] if container.image.tags else "",
            status=container.status,
            ports=ports,
            labels=container.labels or {},
        )

    async def get_base_url(self, container: ContainerInfo, container_port: int = 8080) -> str:
        host_port = container.ports.get(container_port, container_port)
        return f"http://localhost:{host_port}"

    async def health_check(self, base_url: str, path: str = "/health") -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{base_url}{path}")
                return resp.status_code < 500
        except Exception:
            # Try root path as fallback
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get(base_url)
                    return resp.status_code < 500
            except Exception:
                return False

    async def list_containers(self) -> list[ContainerInfo]:
        try:
            client = self._get_client()
            return [self._to_info(c) for c in client.containers.list()]
        except DockerError:
            raise
        except Exception as exc:
            raise DockerError(f"Docker list error: {exc}") from exc
