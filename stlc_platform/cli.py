"""
STLC CLI
========
Command-line interface for the STLC Automation Platform.

Usage:
    stlc run --pipeline config/pipelines/full_stlc.yaml
    stlc run --agent api_test_agent --input spec.json
    stlc validate --stage 3
    stlc agents list
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click

from stlc_platform import __version__


@click.group()
@click.version_option(version=__version__, prog_name="stlc")
def main() -> None:
    """STLC Automation Platform — AI-powered test generation pipeline."""


@main.command()
@click.option(
    "--config", "-c", default="config/stlc_config.yaml",
    help="Config file path.",
)
@click.option(
    "--pipeline", "-p", default=None,
    help="Pipeline YAML file to run.",
)
@click.option(
    "--agent", default=None,
    help="Run a single agent by ID.",
)
@click.option(
    "--input", "-i", "input_file", default=None,
    help="Input artifacts JSON file (for --agent mode).",
)
@click.option(
    "--resume-from", default=None,
    help="Stage ID to resume pipeline from.",
)
@click.option(
    "--output", "-o", default="./output",
    help="Output directory.",
)
@click.option(
    "--max-workers", default=4, type=int,
    help="Max parallel workers for pipeline.",
)
@click.option(
    "--ci", is_flag=True,
    help="CI mode: JSON output, non-interactive.",
)
def run(
    config: str,
    pipeline: Optional[str],
    agent: Optional[str],
    input_file: Optional[str],
    resume_from: Optional[str],
    output: str,
    max_workers: int,
    ci: bool,
) -> None:
    """Run a pipeline or single agent."""
    if agent:
        _run_single_agent(agent, input_file, config, output, ci)
    elif pipeline:
        _run_pipeline(pipeline, config, resume_from, output, max_workers, ci)
    else:
        click.echo("Error: Specify --pipeline or --agent.", err=True)
        raise SystemExit(1)


def _run_single_agent(
    agent_id: str,
    input_file: Optional[str],
    config_path: str,
    output_dir: str,
    ci: bool,
) -> None:
    """Execute a single agent."""
    from stlc_platform.pipeline.agent_registry import AgentRegistry

    registry = AgentRegistry.default()
    try:
        agent_instance = registry.get(agent_id)
    except KeyError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    # Load input artifacts
    artifacts = {}
    if input_file:
        input_path = Path(input_file)
        if not input_path.exists():
            click.echo(f"Error: Input file not found: {input_file}", err=True)
            raise SystemExit(1)
        artifacts = json.loads(input_path.read_text(encoding="utf-8"))

    # Execute
    result = agent_instance.execute(artifacts, {})

    if ci:
        output_data = {
            "success": result.success,
            "errors": result.errors,
            "metadata": result.metadata,
        }
        click.echo(json.dumps(output_data, indent=2, default=str))
    else:
        if result.success:
            click.echo(f"Agent '{agent_id}' completed successfully.")
            for key, value in result.metadata.items():
                click.echo(f"  {key}: {value}")
        else:
            click.echo(f"Agent '{agent_id}' failed:")
            for err in result.errors:
                click.echo(f"  - {err}")

    raise SystemExit(0 if result.success else 1)


def _run_pipeline(
    pipeline_path: str,
    config_path: str,
    resume_from: Optional[str],
    output_dir: str,
    max_workers: int,
    ci: bool,
) -> None:
    """Execute a full pipeline."""
    from stlc_platform.pipeline.agent_registry import AgentRegistry
    from stlc_platform.pipeline.orchestrator import PipelineOrchestrator
    from stlc_platform.pipeline.pipeline_loader import load_pipeline

    # Load pipeline
    try:
        dag = load_pipeline(pipeline_path)
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error loading pipeline: {e}", err=True)
        raise SystemExit(1)

    registry = AgentRegistry.default()
    run_dir = Path(output_dir) / ".stlc_runs" / "latest"

    def on_start(stage_id: str) -> None:
        if not ci:
            click.echo(f"  Running stage: {stage_id}...")

    def on_complete(sr: "StageResult") -> None:  # noqa: F821
        if not ci:
            status = "PASS" if sr.success else ("SKIP" if sr.skipped else "FAIL")
            click.echo(f"  {status}  {sr.stage_id} ({sr.duration_seconds:.1f}s)")

    orchestrator = PipelineOrchestrator(
        dag=dag,
        registry=registry,
        config={},
        run_dir=run_dir,
        max_workers=max_workers,
        on_stage_start=on_start,
        on_stage_complete=on_complete,
    )

    if not ci:
        click.echo(f"Running pipeline: {dag.pipeline_name}")

    result = orchestrator.run(resume_from=resume_from)

    if ci:
        click.echo(result.model_dump_json(indent=2))
    else:
        click.echo(f"\nPipeline: {result.status}")
        click.echo(f"  Completed: {len(result.stages_completed)} stages")
        if result.stages_failed:
            click.echo(f"  Failed: {result.stages_failed}")
        if result.stages_skipped:
            click.echo(f"  Skipped: {result.stages_skipped}")
        click.echo(f"  Duration: {result.total_duration_seconds:.1f}s")

    raise SystemExit(0 if result.status == "completed" else 1)


@main.command()
@click.option(
    "--stage", "-s", type=int, required=True,
    help="Stage number to validate (0-5).",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output.")
def validate(stage: int, verbose: bool) -> None:
    """Run validation gate for a stage."""
    cmd = [sys.executable, "scripts/validate_stage.py", "--stage", str(stage)]
    if verbose:
        cmd.append("--verbose")
    result = subprocess.run(cmd)
    raise SystemExit(result.returncode)


@main.group()
def agents() -> None:
    """Agent management commands."""


@agents.command("list")
def agents_list() -> None:
    """List all registered agents and their capabilities."""
    from stlc_platform.pipeline.agent_registry import AgentRegistry

    registry = AgentRegistry.default()
    caps = registry.list_agents()

    click.echo(f"{'ID':<25} {'Version':<10} {'Description'}")
    click.echo("-" * 80)
    for cap in caps:
        click.echo(f"{cap.agent_id:<25} {cap.agent_version:<10} {cap.description[:44]}")
    click.echo(f"\n{len(caps)} agents registered.")
