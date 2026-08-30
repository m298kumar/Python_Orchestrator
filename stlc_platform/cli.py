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
    "--config",
    "-c",
    default="config/stlc_config.yaml",
    help="Config file path.",
)
@click.option(
    "--pipeline",
    "-p",
    default=None,
    help="Pipeline YAML file to run.",
)
@click.option(
    "--agent",
    default=None,
    help="Run a single agent by ID.",
)
@click.option(
    "--input",
    "-i",
    "input_file",
    default=None,
    help="Input artifacts JSON file (for --agent mode).",
)
@click.option(
    "--resume-from",
    default=None,
    help="Stage ID to resume pipeline from.",
)
@click.option(
    "--output",
    "-o",
    default="./output",
    help="Output directory.",
)
@click.option(
    "--max-workers",
    default=4,
    type=int,
    help="Max parallel workers for pipeline.",
)
@click.option(
    "--ci",
    is_flag=True,
    help="CI mode: JSON output, non-interactive.",
)
@click.option(
    "--profile",
    default=None,
    help="Execution profile (smoke, targeted, regression).",
)
@click.option(
    "--config-profile",
    default=None,
    help="Config profile overlay (web, api).",
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
    profile: Optional[str],
    config_profile: Optional[str],
) -> None:
    """Run a pipeline or single agent."""
    if agent:
        _run_single_agent(agent, input_file, config, output, ci)
    elif pipeline:
        _run_pipeline(
            pipeline,
            config,
            resume_from,
            output,
            max_workers,
            ci,
            profile=profile,
            config_profile=config_profile,
        )
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


def _load_pipeline_config(config_profile: Optional[str]) -> dict:
    """Load pipeline config, optionally applying a config profile overlay."""
    if not config_profile:
        return {}
    try:
        from stlc_platform.core.config_loader import load_config_yaml

        return load_config_yaml(profile=config_profile)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


def _load_execution_profile(profile: Optional[str]):
    """Load an execution profile by name. Returns None if no profile specified."""
    if not profile:
        return None
    from stlc_platform.pipeline.profile_loader import ProfileLoader

    try:
        loader = ProfileLoader()
        return loader.load(profile)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


def _display_pipeline_result(result, ci: bool) -> None:
    """Display pipeline result to stdout in CI or human-friendly format."""
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


def _run_pipeline(
    pipeline_path: str,
    config_path: str,
    resume_from: Optional[str],
    output_dir: str,
    max_workers: int,
    ci: bool,
    profile: Optional[str] = None,
    config_profile: Optional[str] = None,
) -> None:
    """Execute a full pipeline."""
    from stlc_platform.pipeline.agent_registry import AgentRegistry
    from stlc_platform.pipeline.orchestrator import PipelineOrchestrator, StageResult
    from stlc_platform.pipeline.pipeline_loader import load_pipeline
    from stlc_platform.pipeline.skill_loader import SkillLoader

    try:
        dag = load_pipeline(pipeline_path)
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error loading pipeline: {e}", err=True)
        raise SystemExit(1)

    pipeline_config = _load_pipeline_config(config_profile)
    execution_profile = _load_execution_profile(profile)

    domain = pipeline_config.get("project", {}).get("domain", "")
    skill_loader = SkillLoader(domain=domain)

    registry = AgentRegistry.default()
    run_dir = Path(output_dir) / ".stlc_runs" / "latest"

    def on_start(stage_id: str) -> None:
        if not ci:
            click.echo(f"  Running stage: {stage_id}...")

    def on_complete(sr: StageResult) -> None:
        if not ci:
            status = "PASS" if sr.success else ("SKIP" if sr.skipped else "FAIL")
            click.echo(f"  {status}  {sr.stage_id} ({sr.duration_seconds:.1f}s)")

    orchestrator = PipelineOrchestrator(
        dag=dag,
        registry=registry,
        config=pipeline_config,
        run_dir=run_dir,
        max_workers=max_workers,
        on_stage_start=on_start,
        on_stage_complete=on_complete,
        skill_loader=skill_loader,
        execution_profile=execution_profile,
    )

    if not ci:
        click.echo(f"Running pipeline: {dag.pipeline_name}")
        if profile:
            click.echo(f"  Profile: {profile}")
        if config_profile:
            click.echo(f"  Config: {config_profile}")

    result = orchestrator.run(resume_from=resume_from)
    _display_pipeline_result(result, ci)
    raise SystemExit(0 if result.status == "completed" else 1)


@main.command()
@click.option(
    "--stage",
    "-s",
    type=int,
    required=True,
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


@main.group()
def feedback() -> None:
    """Feedback management commands."""


@feedback.command("add")
@click.option("--agent", "-a", required=True, help="Agent ID to add feedback for.")
@click.option(
    "--type",
    "-t",
    "feedback_type",
    default="correction",
    type=click.Choice(["correction", "preference", "constraint"]),
    help="Feedback type.",
)
@click.option("--message", "-m", required=True, help="Feedback message.")
@click.option("--output", "-o", default="./feedback", help="Feedback store path.")
def feedback_add(
    agent: str,
    feedback_type: str,
    message: str,
    output: str,
) -> None:
    """Add feedback for an agent to improve future runs."""
    from stlc_platform.core.contracts import AgentFeedbackArtifact
    from stlc_platform.pipeline.feedback_store import FeedbackStore

    store = FeedbackStore(persist_path=Path(output))
    entry = AgentFeedbackArtifact(
        agent_id=agent,
        feedback_type=feedback_type,
        message=message,
    )
    store.store(entry)
    click.echo(f"Feedback stored for '{agent}' ({store.count} total entries).")


@feedback.command("list")
@click.option("--agent", "-a", default=None, help="Filter by agent ID.")
@click.option("--output", "-o", default="./feedback", help="Feedback store path.")
def feedback_list(agent: Optional[str], output: str) -> None:
    """List stored feedback entries."""
    from stlc_platform.pipeline.feedback_store import FeedbackStore

    store = FeedbackStore(persist_path=Path(output))
    entries = store.list_all(agent_id=agent)

    if not entries:
        click.echo("No feedback entries found.")
        return

    for entry in entries:
        click.echo(
            f"  [{entry.feedback_type}] {entry.agent_id}: {entry.message}"
            f" (applied {entry.applied_count}x)"
        )


@main.group()
def metrics() -> None:
    """Pipeline metrics and quality trends."""


@metrics.command("list")
@click.option(
    "--last",
    "-n",
    "last_n",
    default=20,
    type=int,
    help="Number of recent runs to show.",
)
@click.option(
    "--dir",
    "-d",
    "metrics_dir",
    default="output/metrics",
    help="Metrics directory.",
)
def metrics_list(last_n: int, metrics_dir: str) -> None:
    """List metrics for recent pipeline runs."""
    from stlc_platform.pipeline.metrics_collector import MetricsCollector

    collector = MetricsCollector(metrics_dir=Path(metrics_dir))
    runs = collector.get_trends(last_n=last_n)

    if not runs:
        click.echo("No metrics found.")
        return

    click.echo(
        f"{'Run ID':<14} {'Quality':>8} {'TCs':>5} {'Tokens':>8} "
        f"{'Cost ($)':>9} {'Duration':>9} {'Timestamp'}"
    )
    click.echo("-" * 90)
    for m in runs:
        click.echo(
            f"{m.run_id[:12]:<14} {m.avg_quality_score:>8.3f} "
            f"{m.total_test_cases:>5} {m.tokens_used:>8} "
            f"{m.estimated_cost_usd:>9.4f} {m.generation_time_seconds:>8.1f}s "
            f"{m.timestamp[:19]}"
        )
    click.echo(f"\n{len(runs)} runs shown.")


@metrics.command("trends")
@click.option(
    "--last",
    "-n",
    "last_n",
    default=10,
    type=int,
    help="Number of runs for trend analysis.",
)
@click.option(
    "--dir",
    "-d",
    "metrics_dir",
    default="output/metrics",
    help="Metrics directory.",
)
def metrics_trends(last_n: int, metrics_dir: str) -> None:
    """Show quality and cost trends over recent runs."""
    from stlc_platform.pipeline.metrics_collector import MetricsCollector

    collector = MetricsCollector(metrics_dir=Path(metrics_dir))
    runs = collector.get_trends(last_n=last_n)

    if not runs:
        click.echo("No metrics found for trend analysis.")
        return

    avg_quality = sum(r.avg_quality_score for r in runs) / len(runs)
    avg_time = sum(r.generation_time_seconds for r in runs) / len(runs)
    total_tokens = sum(r.tokens_used for r in runs)
    total_cost = sum(r.estimated_cost_usd for r in runs)

    click.echo(f"Trends over last {len(runs)} runs:")
    click.echo(f"  Avg quality score:    {avg_quality:.3f}")
    click.echo(f"  Avg generation time:  {avg_time:.1f}s")
    click.echo(f"  Total tokens used:    {total_tokens:,}")
    click.echo(f"  Total cost:           ${total_cost:.4f}")

    # Degradation check
    if len(runs) >= 2:
        warning = collector.detect_degradation(runs[0], runs[1:])
        if warning:
            click.echo(f"\n  WARNING: {warning}")


@metrics.command("run")
@click.argument("run_id")
@click.option(
    "--dir",
    "-d",
    "metrics_dir",
    default="output/metrics",
    help="Metrics directory.",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def metrics_run(run_id: str, metrics_dir: str, as_json: bool) -> None:
    """Show metrics for a specific pipeline run."""
    from dataclasses import asdict

    from stlc_platform.pipeline.metrics_collector import MetricsCollector

    collector = MetricsCollector(metrics_dir=Path(metrics_dir))
    m = collector.get_run(run_id)
    if m is None:
        click.echo(f"Error: No metrics found for run '{run_id}'.", err=True)
        raise SystemExit(1)

    if as_json:
        click.echo(json.dumps(asdict(m), indent=2))
    else:
        click.echo(f"Run: {m.run_id}")
        click.echo(f"  Pipeline:      {m.pipeline_name}")
        click.echo(f"  Timestamp:     {m.timestamp}")
        click.echo(f"  Test cases:    {m.total_test_cases}")
        click.echo(f"  Avg quality:   {m.avg_quality_score:.3f}")
        click.echo(f"  Distribution:  {m.quality_distribution}")
        click.echo(f"  Tokens used:   {m.tokens_used:,}")
        click.echo(f"  Cost:          ${m.estimated_cost_usd:.4f}")
        click.echo(f"  Cache hit:     {m.cache_hit_rate:.1%}")
        click.echo(f"  Gen time:      {m.generation_time_seconds:.1f}s")
        click.echo(f"  Coverage:      {m.coverage_pct:.1f}%")
        click.echo(
            f"  Stages:        {m.stages_completed} completed, "
            f"{m.stages_failed} failed, {m.stages_skipped} skipped"
        )
