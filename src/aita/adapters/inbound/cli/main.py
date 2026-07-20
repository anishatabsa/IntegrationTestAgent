"""AITA CLI entry point — powered by Typer + Rich."""
from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

app = typer.Typer(
    name="aita",
    help="AI Integration Test Agent — generate, heal, and learn from integration tests.",
    rich_markup_mode="rich",
)
console = Console()


@app.command("run")
def run_pipeline(
    service: str = typer.Argument(..., help="Service name (must be registered, or supply --repo-url)"),
    branch: str = typer.Option("main", "--branch", "-b", help="Git branch to test"),
    repo_url: str = typer.Option("", "--repo-url", "-r", help="Git repo URL or file:// local path"),
    base_url: str = typer.Option("", "--base-url", help="Running service base URL (e.g. http://localhost:8001)"),
    language: str = typer.Option("python", "--language", "-l", help="Test language: python | java"),
    spec_url: str = typer.Option("", "--spec-url", help="Fetch OpenAPI spec from this URL (default: base_url/openapi.json)"),
    force: bool = typer.Option(False, "--force", "-f", help="Force regenerate all tests"),
    ignore_cache: bool = typer.Option(False, "--no-cache", help="Ignore LLM response cache"),
    no_tests: bool = typer.Option(False, "--no-run", help="Generate only, do not execute"),
    learn: bool = typer.Option(True, "--learn/--no-learn", help="Enrich with RAG knowledge"),
    update_kb: bool = typer.Option(False, "--update-kb", help="Ingest spec into knowledge base"),
    ops: list[str] = typer.Option([], "--op", "-o", help="Run only selected operation IDs"),
    allure: bool = typer.Option(False, "--allure", help="Push results to Allure server"),
    qmetry: bool = typer.Option(False, "--qmetry", help="Push results to QMetry"),
    test_repo_url: str = typer.Option(
        "",
        "--test-repo-url",
        help="GitHub URL of the test-automation repo to publish tests into",
    ),
    test_repo_branch: str = typer.Option(
        "main",
        "--test-repo-branch",
        help="Default branch of the test-automation repo (default: main)",
    ),
    publish: bool = typer.Option(
        True,
        "--publish/--no-publish",
        help="Publish generated tests to GitHub as a PR (requires --test-repo-url or env config)",
    ),
    api_url: str = typer.Option("http://localhost:8000", "--api", help="AITA API base URL"),
):
    """Run the full test generation + execution pipeline for a service."""
    import httpx
    from aita.adapters.inbound.cli.display import print_summary, stream_events

    payload = {
        "service_name": service,
        "branch": branch,
        "repo_url": repo_url,
        "base_url": base_url,
        "language": language,
        "spec_url": spec_url,
        "force_generate": force,
        "ignore_cache": ignore_cache,
        "learn_from_kb": learn,
        "update_kb": update_kb,
        "selected_operations": ops,
        "run_tests": not no_tests,
        "push_to_allure": allure,
        "push_to_qmetry": qmetry,
        "test_automation_repo_url": test_repo_url,
        "test_automation_branch": test_repo_branch,
        "publish_on_gate_pass": publish,
    }

    console.print(Panel(f"[bold cyan]AITA[/] — running pipeline for [yellow]{service}[/]"))

    asyncio.run(stream_events(api_url, payload, console))


@app.command("ingest")
def ingest_knowledge(
    service: str = typer.Argument(..., help="Service name"),
    path: str = typer.Argument(..., help="Path to a .md/.txt/.pdf/.rst file, or a directory"),
    doc_type: str = typer.Option("markdown", "--doc-type", "-t", help="Document type tag stored in metadata"),
    api_url: str = typer.Option("http://localhost:8000", "--api"),
):
    """Ingest documentation into the knowledge base for a service.

    Pass a single file or a directory — all .md / .txt / .pdf / .rst files
    found recursively will be uploaded.  After ingestion, re-run the pipeline
    to generate tests enriched with the new knowledge:

        aita run <service> --repo-url <url> --base-url <url>
    """
    import httpx
    from pathlib import Path as _Path

    _SUPPORTED = {".md", ".txt", ".pdf", ".rst"}
    source = _Path(path)

    if not source.exists():
        console.print(f"[red]Error:[/] path does not exist: {path}")
        raise typer.Exit(code=1)

    files = (
        sorted(f for f in source.rglob("*") if f.is_file() and f.suffix in _SUPPORTED)
        if source.is_dir()
        else ([source] if source.suffix in _SUPPORTED else [])
    )

    if not files:
        console.print(f"[yellow]No supported files found in[/] {path}")
        console.print(f"Supported extensions: {', '.join(sorted(_SUPPORTED))}")
        raise typer.Exit(code=1)

    console.print(Panel(
        f"[bold cyan]AITA Knowledge Ingestion[/]\n"
        f"Service: [yellow]{service}[/]  |  Files: [white]{len(files)}[/]"
    ))

    total_chunks = 0
    url = f"{api_url}/api/v1/knowledge/ingest/{service}"

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("Uploading...", total=len(files))

        for f in files:
            progress.update(task, description=f"Uploading {f.name}...")
            try:
                with open(f, "rb") as fh:
                    resp = httpx.post(
                        url,
                        files={"file": (f.name, fh, "application/octet-stream")},
                        params={"doc_type": doc_type},
                        timeout=120,
                    )
                resp.raise_for_status()
                data = resp.json()
                n = data.get("chunks_ingested", 0)
                total_chunks += n
                console.print(f"  [green]✓[/] {f.name} — {n} chunks")
            except httpx.HTTPStatusError as exc:
                console.print(f"  [red]✗[/] {f.name} — HTTP {exc.response.status_code}: {exc.response.text[:120]}")
            except Exception as exc:
                console.print(f"  [red]✗[/] {f.name} — {exc}")
            progress.advance(task)

    console.print(
        f"\n[bold green]Done![/] Ingested [white]{total_chunks}[/] chunks for [yellow]{service}[/].\n"
        f"Re-run the pipeline to regenerate tests with the new knowledge:\n"
        f"  [cyan]aita run {service} --repo-url <url> --base-url <url>[/]"
    )


@app.command("import-feedback")
def import_feedback(
    yaml_file: str = typer.Argument(..., help="Path to QE feedback YAML file"),
    service: str = typer.Option(..., "--service", "-s", help="Service name"),
    api_url: str = typer.Option("http://localhost:8080", "--api"),
):
    """Import QE feedback YAML and mark affected endpoints for regeneration."""
    console.print(f"[cyan]Importing feedback[/] from {yaml_file}...")
    # TODO: call API
    console.print("[green]✓[/] Feedback imported. Run [cyan]aita run[/] to regenerate.")


@app.command("list")
def list_services(api_url: str = typer.Option("http://localhost:8080", "--api")):
    """List all registered services."""
    import httpx
    try:
        resp = httpx.get(f"{api_url}/api/v1/services")
        data = resp.json()
        table = Table(title="Registered Services")
        table.add_column("Name")
        table.add_column("Language")
        table.add_column("Repo")
        for s in data.get("services", []):
            table.add_row(s.get("name", ""), s.get("language", ""), s.get("repo_url", ""))
        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error:[/] {exc}")


if __name__ == "__main__":
    app()
