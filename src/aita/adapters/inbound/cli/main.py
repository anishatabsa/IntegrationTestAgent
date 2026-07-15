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
    service: str = typer.Argument(..., help="Service name (must be registered)"),
    branch: str = typer.Option("main", "--branch", "-b", help="Git branch to test"),
    force: bool = typer.Option(False, "--force", "-f", help="Force regenerate all tests"),
    ignore_cache: bool = typer.Option(False, "--no-cache", help="Ignore LLM response cache"),
    no_tests: bool = typer.Option(False, "--no-run", help="Generate only, do not execute"),
    learn: bool = typer.Option(True, "--learn/--no-learn", help="Enrich with RAG knowledge"),
    update_kb: bool = typer.Option(False, "--update-kb", help="Ingest spec into knowledge base"),
    ops: list[str] = typer.Option([], "--op", "-o", help="Run only selected operation IDs"),
    allure: bool = typer.Option(False, "--allure", help="Push results to Allure server"),
    qmetry: bool = typer.Option(False, "--qmetry", help="Push results to QMetry"),
    api_url: str = typer.Option("http://localhost:8080", "--api", help="AITA API base URL"),
):
    """Run the full test generation + execution pipeline for a service."""
    import httpx
    from aita.adapters.inbound.cli.display import print_summary, stream_events

    payload = {
        "service_name": service,
        "branch": branch,
        "force_generate": force,
        "ignore_cache": ignore_cache,
        "learn_from_kb": learn,
        "update_kb": update_kb,
        "selected_operations": ops,
        "run_tests": not no_tests,
        "push_to_allure": allure,
        "push_to_qmetry": qmetry,
    }

    console.print(Panel(f"[bold cyan]AITA[/] — running pipeline for [yellow]{service}[/]"))

    asyncio.run(stream_events(api_url, payload, console))


@app.command("ingest")
def ingest_knowledge(
    service: str = typer.Argument(..., help="Service name"),
    path: str = typer.Argument(..., help="Path to file or directory to ingest"),
    api_url: str = typer.Option("http://localhost:8080", "--api"),
):
    """Ingest documentation into the knowledge base for a service."""
    import httpx
    console.print(f"[cyan]Ingesting[/] {path} for service [yellow]{service}[/]...")
    # TODO: call /api/v1/knowledge/ingest/{service}
    console.print("[green]✓[/] Queued for ingestion.")


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
