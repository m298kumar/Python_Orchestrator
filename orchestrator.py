# ── Apply pydantic.v1 patch FIRST — before any chromadb import ───────────────
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(__file__) or ".")
#import pydantic_v1_patch  # noqa — auto-applies on import, must precede chromadb
# ─────────────────────────────────────────────────────────────────────────────

"""
Test Case Orchestrator - Main Entry Point
Reads requirements, generates test cases using Ollama + ChromaDB,
and exports to CSV / Zephyr Scale format.

Usage:
    python orchestrator.py --requirements path/to/requirements.csv
    python orchestrator.py --requirements reqs.txt --format zephyr
    python orchestrator.py --requirements reqs.txt --format both --clear-db
"""

import os
import sys
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from config import config
from requirements_reader import RequirementsReader
from chroma_store import RequirementsVectorStore
from llm_client import OllamaClient
from test_generator import TestCaseGenerator
from exporters.exporters import CSVExporter, ZephyrScaleExporter, JSONReportExporter

console = Console()


def print_banner():
    console.print(
        Panel.fit(
            "[bold cyan]🤖 AI Test Case Orchestrator[/bold cyan]\n"
            "[dim]Powered by Ollama + ChromaDB + Behave[/dim]",
            border_style="cyan",
        )
    )


def print_summary_table(test_cases):
    table = Table(title="Generated Test Cases Summary", show_lines=True)
    table.add_column("TC ID", style="cyan", width=10)
    table.add_column("Req ID", style="yellow", width=10)
    table.add_column("Title", style="white", width=40)
    table.add_column("Type", style="magenta", width=12)
    table.add_column("Priority", style="green", width=10)
    table.add_column("Steps", style="blue", width=6)

    for tc in test_cases[:20]:  # Show first 20
        table.add_row(
            tc.tc_id,
            tc.req_id,
            tc.title[:38] + ".." if len(tc.title) > 40 else tc.title,
            tc.test_type,
            tc.priority,
            str(len(tc.steps)),
        )

    if len(test_cases) > 20:
        table.add_row("...", "...", f"... and {len(test_cases) - 20} more", "", "", "")

    console.print(table)


@click.command()
@click.option(
    "--requirements", "-r",
    required=True,
    help="Path to requirements file (.txt, .csv, .xlsx, .docx, .pdf, .json)",
)
@click.option(
    "--format", "-f",
    "output_format",
    type=click.Choice(["csv", "zephyr", "both"], case_sensitive=False),
    default="both",
    show_default=True,
    help="Output format",
)
@click.option(
    "--model", "-m",
    default=None,
    help=f"Ollama model to use (default: {config.ollama.model})",
)
@click.option(
    "--max-tests",
    type=int,
    default=None,
    help=f"Max test cases per requirement (default: {config.max_test_cases_per_requirement})",
)
@click.option(
    "--output-dir", "-o",
    default=None,
    help=f"Output directory (default: {config.output.output_dir})",
)
@click.option(
    "--clear-db",
    is_flag=True,
    default=False,
    help="Clear ChromaDB requirements + vocab (preserves approved examples)",
)
@click.option(
    "--clear-all",
    is_flag=True,
    default=False,
    help="Clear ALL ChromaDB collections including approved tc_examples",
)
@click.option(
    "--no-chroma",
    is_flag=True,
    default=False,
    help="Skip ChromaDB (faster, no semantic context)",
)
@click.option(
    "--skip-llm-check",
    is_flag=True,
    default=False,
    help="Skip Ollama connection check (for testing)",
)
def run_orchestrator(
    requirements,
    output_format,
    model,
    max_tests,
    output_dir,
    clear_db,
    clear_all,
    no_chroma,
    skip_llm_check,
):
    """
    AI-powered test case generator from requirements files.
    Uses local Ollama LLM + ChromaDB for intelligent test generation.
    """
    print_banner()

    # Apply overrides
    if model:
        config.ollama.model = model
    if output_dir:
        config.output.output_dir = output_dir
    if max_tests:
        config.max_test_cases_per_requirement = max_tests

    console.print(f"[dim]Model:[/dim] {config.ollama.model}")
    console.print(f"[dim]Output:[/dim] {config.output.output_dir}")
    console.print()

    # ── Step 1: Check Ollama connection ────────────────────────────────────────
    if not skip_llm_check:
        console.print("[bold]Step 1/5:[/bold] Checking Ollama connection...")
        llm = OllamaClient()

        if not llm.check_connection():
            console.print(
                "[red]❌ Cannot connect to Ollama![/red]\n"
                "Make sure Ollama is running:\n"
                "  [cyan]ollama serve[/cyan]\n"
                "And pull your model:\n"
                f"  [cyan]ollama pull {config.ollama.model}[/cyan]"
            )
            sys.exit(1)

        available_models = llm.list_models()
        if config.ollama.model not in available_models and available_models:
            console.print(
                f"[yellow]⚠️  Model '{config.ollama.model}' not found.[/yellow]\n"
                f"Available models: {', '.join(available_models)}\n"
                "Pull it with: [cyan]ollama pull {config.ollama.model}[/cyan]"
            )
            if click.confirm("Try to pull the model now?", default=True):
                llm.pull_model(config.ollama.model)

        console.print(
            f"[green]✅ Ollama connected.[/green] Model: {config.ollama.model}"
        )
    else:
        llm = OllamaClient()
        console.print("[yellow]⚠️  Skipping Ollama connection check[/yellow]")

    # ── Step 2: Read requirements ──────────────────────────────────────────────
    console.print("\n[bold]Step 2/5:[/bold] Reading requirements file...")
    reader = RequirementsReader()
    try:
        requirements_list = reader.read(requirements)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]❌ Error reading requirements: {e}[/red]")
        sys.exit(1)

    if not requirements_list:
        console.print("[red]❌ No requirements found in file![/red]")
        sys.exit(1)

    # ── Step 3: Setup ChromaDB ────────────────────────────────────────────────
    vector_store = None
    if not no_chroma:
        console.print("\n[bold]Step 3/5:[/bold] Setting up ChromaDB vector store...")
        try:
            vector_store = RequirementsVectorStore()
            if clear_all:
                vector_store.clear_all()
            elif clear_db:
                vector_store.clear()
            vector_store.add_requirements(requirements_list)
            # Show stats so the user can see how many approved examples are loaded
            stats = vector_store.stats
            console.print(
                f"[dim]ChromaDB:[/dim] "
                f"requirements={stats['requirements']} | "
                f"tc_examples={stats['tc_examples']} | "
                f"domain_vocab={stats['domain_vocab']}"
            )
            if stats['tc_examples'] == 0:
                console.print(
                    "[yellow]No approved examples in tc_examples yet.[/yellow] "
                    "After reviewing output, run: "
                    "[cyan]python mcp_server.py store-example TC-XXXX[/cyan]"
                )
        except Exception as e:
            console.print(
                f"[yellow]⚠️  ChromaDB unavailable ({e}). Continuing without it.[/yellow]"
            )
            vector_store = None
    else:
        console.print("\n[bold]Step 3/5:[/bold] [dim]ChromaDB skipped[/dim]")

    # ── Step 4: Generate test cases ───────────────────────────────────────────
    console.print("\n[bold]Step 4/5:[/bold] Generating test cases with LLM...")
    generator = TestCaseGenerator(llm_client=llm, vector_store=vector_store)

    try:
        test_cases = generator.generate_for_all(requirements_list)
    except Exception as e:
        console.print(f"[red]❌ Test generation failed: {e}[/red]")
        sys.exit(1)

    if not test_cases:
        console.print("[red]❌ No test cases were generated![/red]")
        sys.exit(1)

    print_summary_table(test_cases)

    # ── Step 5: Export ────────────────────────────────────────────────────────
    console.print("\n[bold]Step 5/5:[/bold] Exporting test cases...")
    output_files = []

    if output_format in ("csv", "both"):
        csv_path = CSVExporter().export(test_cases)
        output_files.append(csv_path)

    if output_format in ("zephyr", "both"):
        zephyr_path = ZephyrScaleExporter().export(test_cases)
        output_files.append(zephyr_path)

    # Always export JSON report
    report_path = JSONReportExporter().export(test_cases, len(requirements_list))
    output_files.append(report_path)

    # ── Done ──────────────────────────────────────────────────────────────────
    console.print(
        Panel.fit(
            f"[bold green]✅ Done![/bold green]\n\n"
            f"Requirements processed: [cyan]{len(requirements_list)}[/cyan]\n"
            f"Test cases generated:   [cyan]{len(test_cases)}[/cyan]\n\n"
            f"Output files:\n"
            + "\n".join(f"  📄 {f}" for f in output_files),
            border_style="green",
        )
    )


if __name__ == "__main__":
    run_orchestrator()