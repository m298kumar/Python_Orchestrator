"""
STLC Test Generation Pipeline Runner
=====================================
Uses the new Stage 1 modular architecture to read requirements,
generate test cases via LLM, and export results to CSV / Zephyr / JSON.

Usage:
    python run_pipeline.py --requirements <file>
    python run_pipeline.py --requirements <file> --format csv --max-tests 3
    python run_pipeline.py --requirements <file> --no-chroma --skip-llm-check
    python run_pipeline.py --fixtures  # run against all 3 built-in fixture files

See --help for full options.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from stlc_platform.core.config_loader import config
from stlc_platform.core.llm import create_llm_client
from stlc_platform.core.contracts import TestCaseArtifact
from stlc_platform.agents.requirements_agent.reader import RequirementsReader
from stlc_platform.agents.requirements_agent.agent import TestGenerationAgent
from stlc_platform.exporters import CSVExporter, ZephyrScaleExporter, JSONReportExporter

console = Console(force_terminal=True)

# -- Paths --------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"


# -- Helpers ------------------------------------------------------------------


def _setup_chroma(skip: bool):
    """Optionally set up the ChromaDB vector store. Returns store or None."""
    if skip:
        console.print("[dim]Skipping ChromaDB (--no-chroma)[/dim]")
        return None
    try:
        from stlc_platform.core.storage import RequirementsVectorStore

        store = RequirementsVectorStore()
        console.print("[green]OK[/green] ChromaDB vector store ready")
        return store
    except Exception as exc:
        console.print(
            f"[yellow]WARN ChromaDB unavailable ({exc}). Continuing without vector store.[/yellow]"
        )
        return None


def _check_llm(client, skip: bool) -> bool:
    """Check LLM connectivity. Returns True if OK or skipped."""
    if skip:
        console.print("[dim]Skipping LLM connection check (--skip-llm-check)[/dim]")
        return True
    try:
        ok = client.check_connection()
        if ok:
            console.print(f"[green]OK[/green] LLM connected ({type(client).__name__})")
            return True
        console.print("[red]FAIL LLM check_connection() returned False[/red]")
        return False
    except Exception as exc:
        console.print(f"[red]FAIL LLM connection failed: {exc}[/red]")
        return False


def _read_requirements(path: str):
    """Read requirements from a file using the migrated RequirementsReader."""
    reader = RequirementsReader()
    reqs = reader.read(path)
    if not reqs:
        console.print(f"[red]FAIL No requirements found in {path}[/red]")
        return []
    console.print(
        f"[green]OK[/green] Loaded [bold]{len(reqs)}[/bold] requirements from {Path(path).name}"
    )
    return reqs


def _export_results(
    test_cases: List[TestCaseArtifact],
    requirements_count: int,
    fmt: str,
    output_dir: Optional[str] = None,
):
    """Export test cases to the requested formats."""
    if output_dir:
        config.output.output_dir = output_dir

    exported_files = []

    if fmt in ("csv", "both", "all"):
        try:
            csv_path = CSVExporter().export(test_cases)
            console.print(f"  [green]OK[/green] CSV  -> {csv_path}")
            exported_files.append(csv_path)
        except Exception as exc:
            console.print(f"  [red]FAIL CSV export failed: {exc}[/red]")

    if fmt in ("zephyr", "both", "all"):
        try:
            zephyr_path = ZephyrScaleExporter().export(test_cases)
            console.print(f"  [green]OK[/green] Zephyr -> {zephyr_path}")
            exported_files.append(zephyr_path)
        except Exception as exc:
            console.print(f"  [red]FAIL Zephyr export failed: {exc}[/red]")

    if fmt in ("json", "both", "all"):
        try:
            json_path = JSONReportExporter().export(test_cases, requirements_count)
            console.print(f"  [green]OK[/green] JSON -> {json_path}")
            exported_files.append(json_path)
        except Exception as exc:
            console.print(f"  [red]FAIL JSON export failed: {exc}[/red]")

    return exported_files


def _print_summary(test_cases: List[TestCaseArtifact], elapsed: float):
    """Print a summary table of generated test cases."""
    table = Table(title="Generated Test Cases", show_lines=True)
    table.add_column("TC ID", style="cyan", no_wrap=True)
    table.add_column("Req ID", style="green")
    table.add_column("Type", style="magenta")
    table.add_column("Priority")
    table.add_column("Title", max_width=50)

    for tc in test_cases:
        priority_style = {
            "Critical": "bold red",
            "High": "red",
            "Medium": "yellow",
            "Low": "dim",
        }.get(tc.priority, "")
        table.add_row(
            tc.tc_id,
            tc.req_id,
            tc.test_type,
            f"[{priority_style}]{tc.priority}[/{priority_style}]" if priority_style else tc.priority,
            tc.title,
        )

    console.print()
    console.print(table)
    console.print(
        f"\n[bold]Total:[/bold] {len(test_cases)} test cases generated in {elapsed:.1f}s"
    )


# -- Main Pipeline ------------------------------------------------------------


def run_pipeline(
    requirements_path: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_tests: Optional[int] = None,
    include_negative: bool = True,
    include_edge: bool = True,
    tc_format: str = "gherkin",
    export_format: str = "all",
    output_dir: Optional[str] = None,
    no_chroma: bool = False,
    skip_llm_check: bool = False,
    domain: Optional[str] = None,
) -> List[TestCaseArtifact]:
    """
    Run the full test generation pipeline.

    Returns the list of generated TestCaseArtifact objects.
    """
    console.print(
        Panel(
            "[bold blue]STLC Test Generation Pipeline[/bold blue]\n"
            f"Requirements: {requirements_path}",
            border_style="blue",
        )
    )

    # Step 1: LLM Client
    console.print("\n[bold]Step 1/5:[/bold] Setting up LLM client...")
    effective_provider = provider or config.llm_provider
    llm_client = create_llm_client(effective_provider)
    if model:
        llm_client.model = model
    elif effective_provider == "ollama":
        llm_client.model = config.ollama.model

    if not _check_llm(llm_client, skip_llm_check):
        console.print("[red]Aborting: LLM is not reachable.[/red]")
        return []

    # Step 2: Read requirements
    console.print("\n[bold]Step 2/5:[/bold] Reading requirements...")
    reqs = _read_requirements(requirements_path)
    if not reqs:
        return []

    # Step 3: ChromaDB (optional)
    console.print("\n[bold]Step 3/5:[/bold] Setting up vector store...")
    vector_store = _setup_chroma(no_chroma)

    # Step 4: Generate test cases
    console.print("\n[bold]Step 4/5:[/bold] Generating test cases...")
    start = time.time()

    agent = TestGenerationAgent()

    generation_config = {
        "max_tests": max_tests or config.max_test_cases_per_requirement,
        "include_negative": include_negative,
        "include_edge": include_edge,
        "tc_format": tc_format,
    }
    if domain:
        generation_config["domain"] = domain

    artifacts = {
        "requirements": reqs,
        "llm_client": llm_client,
    }
    if vector_store:
        artifacts["vector_store"] = vector_store

    result = agent.execute(artifacts=artifacts, config=generation_config)
    elapsed = time.time() - start

    if not result.success:
        console.print(f"[red]FAIL Generation failed:[/red]")
        for err in result.errors:
            console.print(f"  [red]- {err}[/red]")
        return []

    test_cases = result.artifacts["test_cases"]
    console.print(
        f"[green]OK[/green] Generated [bold]{len(test_cases)}[/bold] test cases "
        f"for {result.metadata.get('total_requirements', '?')} requirements "
        f"(domain: {result.metadata.get('domain', 'auto-detected')})"
    )

    _print_summary(test_cases, elapsed)

    # Step 5: Export
    console.print(f"\n[bold]Step 5/5:[/bold] Exporting results ({export_format})...")
    _export_results(test_cases, len(reqs), export_format, output_dir)

    console.print("\n[bold green]OK Pipeline complete![/bold green]")
    return test_cases


def run_fixtures(
    *,
    max_tests: int = 2,
    export_format: str = "all",
    output_dir: Optional[str] = None,
    no_chroma: bool = True,
    skip_llm_check: bool = False,
    provider: Optional[str] = None,
    model: Optional[str] = None,
):
    """Run the pipeline against all 3 built-in fixture files."""
    fixtures = [
        FIXTURES_DIR / "requirements_ecommerce.json",
        FIXTURES_DIR / "requirements_healthcare.json",
        FIXTURES_DIR / "requirements_banking.json",
    ]

    all_test_cases = []
    for fixture in fixtures:
        if not fixture.exists():
            console.print(f"[yellow]Skipping missing fixture: {fixture.name}[/yellow]")
            continue
        console.print(f"\n{'='*60}")
        tcs = run_pipeline(
            str(fixture),
            provider=provider,
            model=model,
            max_tests=max_tests,
            include_negative=True,
            include_edge=True,
            tc_format="gherkin",
            export_format=export_format,
            output_dir=output_dir or f"./output/{fixture.stem}",
            no_chroma=no_chroma,
            skip_llm_check=skip_llm_check,
        )
        all_test_cases.extend(tcs)

    console.print(f"\n{'='*60}")
    console.print(
        f"[bold green]All fixtures complete! Total: {len(all_test_cases)} test cases[/bold green]"
    )
    return all_test_cases


# -- CLI ----------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="STLC Test Generation Pipeline -- generate test cases from requirements",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py --requirements docs/requirements.txt
  python run_pipeline.py --requirements reqs.json --format csv --max-tests 3
  python run_pipeline.py --requirements reqs.json --provider ollama --model phi4-mini:3.8b
  python run_pipeline.py --fixtures --max-tests 2 --no-chroma
  python run_pipeline.py --fixtures --skip-llm-check  # if LLM is known to be running
        """,
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--requirements", "-r",
        type=str,
        help="Path to requirements file (.txt, .csv, .xlsx, .docx, .pdf, .json, .md)",
    )
    source.add_argument(
        "--fixtures",
        action="store_true",
        help="Run against all 3 built-in fixture files (ecommerce, healthcare, banking)",
    )

    parser.add_argument(
        "--format", "-f",
        choices=["csv", "zephyr", "json", "both", "all"],
        default="all",
        help="Export format (default: all)",
    )
    parser.add_argument(
        "--max-tests", "-m",
        type=int,
        default=None,
        help=f"Max test cases per requirement (default: {config.max_test_cases_per_requirement})",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai", "anthropic"],
        default=None,
        help=f"LLM provider (default: {config.llm_provider})",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override LLM model name",
    )
    parser.add_argument(
        "--domain",
        type=str,
        default=None,
        help="Explicit domain label (e.g. 'healthcare', 'banking'). Auto-detected if omitted.",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default=None,
        help=f"Output directory (default: {config.output.output_dir})",
    )
    parser.add_argument(
        "--tc-format",
        choices=["gherkin", "standard"],
        default="gherkin",
        help="Test case format (default: gherkin)",
    )
    parser.add_argument(
        "--no-negative",
        action="store_true",
        help="Disable negative test generation",
    )
    parser.add_argument(
        "--no-edge",
        action="store_true",
        help="Disable edge case test generation",
    )
    parser.add_argument(
        "--no-chroma",
        action="store_true",
        help="Skip ChromaDB vector store",
    )
    parser.add_argument(
        "--skip-llm-check",
        action="store_true",
        help="Skip LLM connection check",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.fixtures:
        run_fixtures(
            max_tests=args.max_tests or 2,
            export_format=args.format,
            output_dir=args.output_dir,
            no_chroma=args.no_chroma,
            skip_llm_check=args.skip_llm_check,
            provider=args.provider,
            model=args.model,
        )
    else:
        run_pipeline(
            args.requirements,
            provider=args.provider,
            model=args.model,
            max_tests=args.max_tests,
            include_negative=not args.no_negative,
            include_edge=not args.no_edge,
            tc_format=args.tc_format,
            export_format=args.format,
            output_dir=args.output_dir,
            no_chroma=args.no_chroma,
            skip_llm_check=args.skip_llm_check,
            domain=args.domain,
        )


if __name__ == "__main__":
    main()
