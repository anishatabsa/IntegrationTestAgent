"""Step 13 — Publish healed tests to the GitHub test-automation repo as a PR.

Branching strategy
------------------
One branch per service: ``aita/{service_name}``  (e.g. ``aita/ecommerce``).

- If an open PR already exists on that branch → push a new commit and update
  the PR body with the latest run summary.
- If no open PR exists → create (or reset) the branch and open a new PR.

Repo housekeeping (one-time, committed to default branch)
---------------------------------------------------------
- ``.gitignore`` — standard Python test-project ignore rules.
- ``tests/{service}/VERSION`` — semver string, patch-bumped on every publish.

Skip conditions
---------------
- Quality gate failed and ``publish_on_gate_pass`` is True (default).
- No test-automation repo URL configured.
- No healed tests to publish.

Any exception inside the publish logic is caught and stored as a warning so
that a publishing failure never breaks the overall pipeline result.
"""
from __future__ import annotations

import os
import re as _re
from datetime import datetime, timezone

import structlog

from aita.core.pipeline.base_step import BaseStep
from aita.core.pipeline.context import PipelineContext
from aita.domain.enums import PipelineStep, RunStatus

logger = structlog.get_logger()


# ── constants ─────────────────────────────────────────────────────────────────

_GITIGNORE_CONTENT = """\
# ── Python ────────────────────────────────────────────────────────────────────
__pycache__/
*.py[cod]
*.pyo
*.pyd
*.egg-info/
dist/
build/

# ── Test artefacts ────────────────────────────────────────────────────────────
.pytest_cache/
.coverage
htmlcov/
coverage.xml
test-results/
allure-results/
allure-report/
*.xml

# ── Virtual environments ──────────────────────────────────────────────────────
.venv/
venv/
env/
.python-version

# ── IDEs ──────────────────────────────────────────────────────────────────────
.idea/
.vscode/
*.swp
*.swo

# ── OS ────────────────────────────────────────────────────────────────────────
.DS_Store
Thumbs.db

# ── Secrets — never commit tokens or keys ────────────────────────────────────
.env
*.key
*.pem
"""

_DEFAULT_VERSION = "0.1.0"


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_github_owner_repo(url: str) -> tuple[str, str] | None:
    """Return (owner, repo) from a GitHub HTTPS URL, or None if unparseable."""
    url = url.rstrip("/").removesuffix(".git")
    if "github.com/" not in url:
        return None
    after = url.split("github.com/", 1)[1]
    parts = after.split("/")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None


def _resolve_token(ctx: PipelineContext) -> str:
    """Token precedence: settings (.env) → OS env var."""
    from aita.config import settings
    # Prefer the value from .env (settings) so that a stale shell export
    # doesn't shadow the correct token.
    return settings.github_token or os.environ.get("GITHUB_TOKEN", "")


def _file_path_in_repo(service: str, test_case) -> str:  # noqa: ANN001
    """Derive the path for a test file inside the automation repo."""
    name = test_case.name
    if not name.startswith("test_"):
        name = f"test_{name}"
    ext = "java" if str(test_case.language) == "java" else "py"
    return f"tests/{service}/{name}.{ext}"


def _bump_version(version_str: str) -> str:
    """Bump the patch component of a semver string (MAJOR.MINOR.PATCH)."""
    parts = version_str.strip().split(".")
    if len(parts) == 3:
        try:
            major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
            return f"{major}.{minor}.{patch + 1}"
        except ValueError:
            pass
    return _DEFAULT_VERSION


def _extract_test_methods(content: str) -> dict[str, str]:
    """Return {method_name: source_block} for every class-level ``def`` in a pytest file.

    Captures ALL methods — setUp, tearDown, helper methods, and test_* — so that
    the merge correctly preserves or updates setup and helper methods alongside
    test methods. Each block extends from the method's ``def`` line to the start
    of the next class-level ``def`` (or end of file).
    """
    matches = [(m.group(1), m.start())
               for m in _re.finditer(r'^    def (\w+)\b', content, _re.MULTILINE)]
    methods: dict[str, str] = {}
    for i, (name, start) in enumerate(matches):
        end = matches[i + 1][1] if i + 1 < len(matches) else len(content)
        methods[name] = content[start:end].rstrip()
    return methods


def _merge_test_content(existing: str, new: str) -> str:
    """Patch the existing file with regenerated methods.

    The existing file in the repo is the source of truth:
    - Method in BOTH → replace the existing body with the new one (improvement wins).
    - Method ONLY in new → append at the end (new scenario from KB or prompt).
    - Method ONLY in existing → left completely untouched; it stays where it is.

    This means tests that weren't regenerated require no special handling —
    they simply remain in the file. Deletion requires explicit QE instruction
    (not yet implemented).
    """
    existing_methods = _extract_test_methods(existing)
    new_methods = _extract_test_methods(new)

    result = existing

    # Replace regenerated methods in-place
    for name, new_body in new_methods.items():
        if name in existing_methods:
            old_body = existing_methods[name]
            if old_body != new_body:
                result = result.replace(old_body, new_body, 1)

    # Append brand-new methods (first appearance — not in the existing file yet)
    truly_new = {name: body for name, body in new_methods.items()
                 if name not in existing_methods}
    if truly_new:
        result = result.rstrip()
        for body in truly_new.values():
            result += "\n\n" + body
        result += "\n"

    return result


def _upsert_file(repo, path: str, content: str, branch: str, commit_msg: str) -> bool:
    """Create or update a single file on *branch*.

    Returns True if a commit was made (file was new or merged content changed),
    False if the content was identical (no commit needed).

    Uses method-level merging so that:
    - New / updated test methods replace their old counterparts.
    - Test methods only in the existing file are preserved (never silently deleted).
    """
    from github import GithubException
    try:
        existing = repo.get_contents(path, ref=branch)
        existing_content = existing.decoded_content.decode("utf-8", errors="ignore")
        merged = _merge_test_content(existing_content, content)
        if existing_content == merged:
            return False  # no effective change — skip commit
        repo.update_file(path=path, message=commit_msg,
                         content=merged, sha=existing.sha, branch=branch)
        return True
    except GithubException:
        repo.create_file(path=path, message=commit_msg,
                         content=content, branch=branch)
        return True


def _build_pr_body(ctx: PipelineContext, summary: dict, version: str) -> str:
    """Markdown PR body for QE review."""
    service = ctx.options.service_name
    run_id = str(ctx.run_id)
    pass_rate = summary["pass_rate"]
    total = summary["tests_total"]
    passing = summary["tests_passing"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    file_lines = ""
    if ctx.healed_tests:
        paths = sorted(_file_path_in_repo(service, tc) for tc in ctx.healed_tests.values())
        file_lines = "\n".join(f"- `{p}`" for p in paths)

    failures = [r for r in ctx.test_results if r.status in ("failed", "error")]
    failure_section = ""
    if failures:
        lines = []
        for f in failures[:20]:
            first_line = (f.error_message or "").splitlines()[0][:120]
            lines.append(f"- {first_line or 'unknown error'}")
        failure_section = (
            "\n### Known Failures\n"
            + "\n".join(lines)
            + ("\n\n_(showing first 20 of {})_".format(len(failures)) if len(failures) > 20 else "")
        )

    return f"""\
## AITA — Auto-generated Integration Tests

| | |
|---|---|
| **Service** | `{service}` |
| **Version** | `{version}` |
| **Run ID** | `{run_id}` |
| **Generated** | {now} |
| **Pass Rate** | {pass_rate:.1f}% ({passing}/{total}) |

### Files Changed
{file_lines}
{failure_section}

### QE Review Checklist
- [ ] Test naming and coverage look reasonable
- [ ] Assertions match the service contract
- [ ] No sensitive data hardcoded in test payloads
- [ ] Edge cases and negative tests are present
- [ ] Merge when satisfied, or push additional commits to this branch

> _This PR was opened automatically by AITA. Failures listed above are known issues at generation time._
"""


# ── step ─────────────────────────────────────────────────────────────────────

class PublishStep(BaseStep):
    """Push healed tests to the GitHub test-automation repo and open (or update) a PR."""

    @property
    def step_id(self) -> PipelineStep:
        return PipelineStep.PUBLISH

    def should_skip(self, ctx: PipelineContext) -> bool:
        from aita.config import settings

        repo_url = ctx.options.test_automation_repo_url or settings.test_automation_repo_url
        if not repo_url:
            logger.info("publish_skipped", reason="no_repo_url")
            return True

        if not ctx.healed_tests:
            logger.info("publish_skipped", reason="no_tests")
            return True

        if ctx.options.publish_on_gate_pass and ctx.status == RunStatus.FAILED:
            logger.info("publish_skipped", reason="gate_failed")
            return True

        return False

    async def _execute(self, ctx: PipelineContext) -> None:
        import asyncio
        try:
            # All PyGithub calls are synchronous (uses requests under the hood).
            # Run them in a thread pool so we don't block the asyncio event loop.
            await asyncio.to_thread(self._publish_sync, ctx)
        except Exception as exc:
            logger.warning("publish_step_error", error=str(exc), exc_info=True)
            ctx.warn(f"PublishStep: {exc}")

    def _publish_sync(self, ctx: PipelineContext) -> None:
        """Synchronous publish body — runs in a thread pool via asyncio.to_thread()."""
        from github import Github, GithubException
        from aita.config import settings

        token = _resolve_token(ctx)
        if not token:
            ctx.warn("PublishStep: GITHUB_TOKEN not set — skipping publish")
            return

        repo_url = ctx.options.test_automation_repo_url or settings.test_automation_repo_url
        parsed = _parse_github_owner_repo(repo_url)
        if not parsed:
            ctx.warn(f"PublishStep: cannot parse GitHub URL '{repo_url}'")
            return

        owner, repo_name = parsed
        gh = Github(token)
        try:
            repo = gh.get_repo(f"{owner}/{repo_name}")
        except GithubException as exc:
            ctx.warn(f"PublishStep: cannot access repo '{owner}/{repo_name}': {exc}")
            return

        service = ctx.options.service_name
        branch_name = f"aita/{service}"
        default_branch = repo.default_branch

        # ── 1. Ensure .gitignore is on the PR branch ─────────────────────────
        # Committed to the feature branch so QE sees it in the PR review.
        # After the first merge to main it's inherited by all future branches,
        # and _upsert_file will detect no change and skip the commit.
        try:
            _upsert_file(
                repo, ".gitignore", _GITIGNORE_CONTENT, branch_name,
                "chore: add .gitignore for Python test project",
            )
            logger.info("publish_gitignore_ensured")
        except GithubException as exc:
            logger.warning("publish_gitignore_failed", error=str(exc))

        # ── 2. Ensure the service branch exists ───────────────────────────────
        try:
            repo.get_branch(branch_name)
            logger.info("publish_branch_exists", branch=branch_name)
        except GithubException:
            try:
                default_sha = repo.get_branch(default_branch).commit.sha
                repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=default_sha)
                logger.info("publish_branch_created", branch=branch_name)
            except GithubException as exc:
                ctx.warn(f"PublishStep: could not create branch '{branch_name}': {exc}")
                return

        # ── 3. Read current version and bump it ───────────────────────────────
        version_path = f"tests/{service}/VERSION"
        current_version = _DEFAULT_VERSION
        try:
            vf = repo.get_contents(version_path, ref=branch_name)
            current_version = vf.decoded_content.decode("utf-8", errors="ignore").strip()
        except GithubException:
            pass  # file doesn't exist yet — use default

        new_version = _bump_version(current_version)
        logger.info("publish_version", previous=current_version, new=new_version, service=service)

        # ── 4. Commit all healed test files (only if content changed) ────────
        run_short = str(ctx.run_id)[:8]
        files_changed = 0
        for op_id, test_case in ctx.healed_tests.items():
            file_path = _file_path_in_repo(service, test_case)
            commit_msg = f"chore(aita): upsert {file_path.split('/')[-1]} [{run_short}]"
            try:
                changed = _upsert_file(repo, file_path, test_case.content, branch_name, commit_msg)
                if changed:
                    files_changed += 1
                    logger.debug("publish_file_committed", path=file_path)
            except GithubException as exc:
                logger.warning("publish_file_error", path=file_path, error=str(exc))

        logger.info("publish_files_done", changed=files_changed, total=len(ctx.healed_tests), branch=branch_name)

        # ── 5. Check for an existing open PR ─────────────────────────────────
        open_prs = list(
            repo.get_pulls(state="open", head=f"{owner}:{branch_name}", base=default_branch)
        )
        is_new_pr = len(open_prs) == 0

        # If no test files changed, skip version bump and PR creation/update.
        # - Existing PR: point ctx.pr_url at it so callers can surface the link.
        # - No PR at all: nothing to do; the branch is already up-to-date.
        if files_changed == 0:
            if not is_new_pr:
                logger.info("publish_no_changes", service=service, pr_url=open_prs[0].html_url)
                ctx.pr_url = open_prs[0].html_url
                for test_case in ctx.healed_tests.values():
                    test_case.git_ref = ctx.pr_url
            else:
                logger.info("publish_no_changes_no_pr", service=service)
            return

        # ── 6. Bump VERSION only when tests actually changed ──────────────────
        if files_changed > 0:
            try:
                _upsert_file(
                    repo, version_path, new_version + "\n", branch_name,
                    f"chore(aita): bump {service} version {current_version} → {new_version} [{run_short}]",
                )
                logger.info("publish_version_committed", version=new_version)
            except GithubException as exc:
                logger.warning("publish_version_commit_failed", error=str(exc))
                new_version = current_version  # revert to unchanged version in PR title
        else:
            new_version = current_version  # nothing changed, keep current version

        # ── 7. Create or update PR ────────────────────────────────────────────
        summary = ctx.summary()
        pr_body = _build_pr_body(ctx, summary, new_version)
        pr_title = f"[AITA] Integration tests — {service} v{new_version}"

        if open_prs:
            pr = open_prs[0]
            try:
                pr.edit(title=pr_title, body=pr_body)
            except GithubException as exc:
                logger.warning("publish_pr_update_failed", error=str(exc))
            logger.info("publish_pr_updated", pr_url=pr.html_url, number=pr.number)
        else:
            try:
                pr = repo.create_pull(
                    title=pr_title,
                    body=pr_body,
                    head=branch_name,
                    base=default_branch,
                )
                logger.info("publish_pr_created", pr_url=pr.html_url, number=pr.number)
            except GithubException as exc:
                ctx.warn(f"PublishStep: could not create PR: {exc}")
                return

        ctx.pr_url = pr.html_url
        for test_case in ctx.healed_tests.values():
            test_case.git_ref = pr.html_url
