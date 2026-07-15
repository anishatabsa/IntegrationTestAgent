"""REST router: /api/v1/webhooks — GitLab and Jenkins CI triggers."""
from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


def _verify_gitlab(payload: bytes, token: str, secret: str) -> bool:
    return hmac.compare_digest(token, secret)


def _verify_jenkins(payload: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_gitlab_token: str = Header(default=""),
):
    """Receive GitLab push / merge-request webhook and trigger pipeline."""
    from aita.config import settings
    if not hmac.compare_digest(x_gitlab_token, settings.ci_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    payload = await request.json()
    branch = payload.get("ref", "").removeprefix("refs/heads/")
    repo_url = payload.get("repository", {}).get("git_http_url", "")
    service_name = payload.get("project", {}).get("name", "")

    # TODO: resolve service_name from repo_url, trigger orchestrator
    return {"status": "accepted", "branch": branch, "service": service_name}


@router.post("/jenkins")
async def jenkins_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_jenkins_signature_256: str = Header(default=""),
):
    """Receive Jenkins post-build webhook and trigger pipeline."""
    from aita.config import settings
    body = await request.body()

    if not _verify_jenkins(body, x_jenkins_signature_256, settings.ci_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    service_name = payload.get("name", "")
    branch = payload.get("branch", "main")

    # TODO: trigger orchestrator
    return {"status": "accepted", "service": service_name, "branch": branch}
