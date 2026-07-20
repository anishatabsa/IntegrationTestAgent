"""Rich terminal display helpers for CLI streaming output."""
from __future__ import annotations

import asyncio
import json

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

_STEP_EMOJI = {
    "git_pull": "📥",
    "spec_parse": "📄",
    "source_scan": "🔍",
    "endpoint_diff": "⚡",
    "rag_enrich": "🧠",
    "generate": "✨",
    "heal": "🩹",
    "persist": "💾",
    "execute": "🚀",
    "feedback": "📊",
    "report": "📈",
    "gate": "🚦",
}


async def stream_events(api_url: str, payload: dict, console: Console) -> None:
    """POST a run request and stream SSE events to the terminal."""
    # connect/write have a generous timeout; read=None so the SSE stream can
    # wait indefinitely between events (generate step can take 10+ minutes).
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=30, read=None, write=60, pool=30)
    ) as client:
        # Trigger run
        resp = await client.post(f"{api_url}/api/v1/runs", json=payload)
        if resp.status_code not in (200, 201, 202):
            console.print(f"[red]API error {resp.status_code}:[/] {resp.text}")
            return

        run_id = resp.json().get("run_id")
        console.print(f"[dim]Run ID: {run_id}[/]")

        # Stream events
        # NOTE: transient=False so completed/failed steps remain visible after the run.
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        )
        task = progress.add_task("Starting pipeline...", total=None)
        progress.start()

        summary_data: dict = {}
        final_event: str = ""
        final_message: str = ""

        try:
            async with client.stream("GET", f"{api_url}/api/v1/runs/{run_id}/stream") as stream:
                async for line in stream.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        data = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue

                    event_type = data.get("event_type", "")
                    step = data.get("step", "")
                    message = data.get("message", "")
                    emoji = _STEP_EMOJI.get(step, "▸")

                    if event_type == "step_started":
                        progress.update(task, description=f"{emoji} Running {step}...")
                    elif event_type == "step_completed":
                        progress.update(task, description=f"{emoji} {step} ✓")
                        console.print(f"  [green]✓[/] {emoji} {step}", highlight=False)
                    elif event_type in ("step_failed", "step_skipped"):
                        label = "skipped" if event_type == "step_skipped" else f"✗ {message}"
                        console.print(f"  [{'yellow' if 'skip' in event_type else 'red'}]{label}[/] {emoji} {step}", highlight=False)
                    elif event_type == "pipeline_completed":
                        summary_data = data.get("data", {})
                        final_event = "completed"
                        break
                    elif event_type == "pipeline_failed":
                        summary_data = data.get("data", {})
                        final_message = message
                        final_event = "failed"
                        break
                    elif event_type == "error":
                        final_message = message
                        final_event = "error"
                        break
        finally:
            progress.stop()

        console.print()  # blank line after progress
        if final_event == "completed":
            print_summary(summary_data, console)
        elif final_event == "failed":
            console.print(Panel(f"[red]Pipeline FAILED:[/] {final_message}", style="red"))
            if summary_data:
                print_summary(summary_data, console)
        elif final_event == "error":
            console.print(f"[red]Error:[/] {final_message}")


def print_summary(summary: dict, console: Console) -> None:
    if not summary:
        return
    status = summary.get("status", "unknown")
    color = "green" if status == "completed" else "red"
    console.print()
    console.print(Panel(
        f"[bold {color}]Pipeline {status.upper()}[/]\n\n"
        f"Endpoints: {summary.get('endpoints_total', 0)} total, "
        f"{summary.get('endpoints_changed', 0)} changed\n"
        f"Tests: {summary.get('tests_generated', 0)} generated, "
        f"{summary.get('tests_healed', 0)} healed\n"
        f"Results: [bold]{summary.get('tests_passing', 0)}/{summary.get('tests_total', 0)}[/] "
        f"passing ([bold]{summary.get('pass_rate', 0)}%[/])"
        + (f", {summary.get('tests_errors', 0)} collection errors" if summary.get('tests_errors') else "")
        + "\n"
        f"Tokens: {sum(summary.get('token_usage', {}).values())}",
        title="Summary",
        style=color,
    ))
    if summary.get("errors"):
        for err in summary["errors"]:
            console.print(f"  [red]•[/] {err}")
    if summary.get("warnings"):
        for w in summary["warnings"]:
            console.print(f"  [yellow]⚠[/] {w}")
