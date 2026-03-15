"""
Behave environment.py - setup/teardown hooks for test orchestrator BDD tests
"""
import os
import sys
import shutil
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from rich.console import Console

console = Console()


def before_all(context):
    """Suite-level setup"""
    console.print("\n[bold cyan]🚀 Starting Behave Test Suite[/bold cyan]")

    # Create a temp output directory for tests
    context.test_output_dir = tempfile.mkdtemp(prefix="orchestrator_test_")
    context.test_chroma_dir = tempfile.mkdtemp(prefix="chroma_test_")

    # Override config for testing
    from config import config
    config.output.output_dir = context.test_output_dir
    config.chromadb.persist_directory = context.test_chroma_dir
    config.chromadb.collection_name = "test_requirements"

    context.config_obj = config


def after_all(context):
    """Suite-level teardown"""
    # Clean up temp directories
    if hasattr(context, "test_output_dir") and os.path.exists(context.test_output_dir):
        shutil.rmtree(context.test_output_dir, ignore_errors=True)

    if hasattr(context, "test_chroma_dir") and os.path.exists(context.test_chroma_dir):
        shutil.rmtree(context.test_chroma_dir, ignore_errors=True)

    console.print("\n[bold green]✅ Behave Test Suite Complete[/bold green]")


def before_scenario(context, scenario):
    """Per-scenario setup"""
    context.generated_test_cases = []
    context.current_requirements = []
    context.last_error = None
    console.print(f"\n[dim]▶ {scenario.name}[/dim]")


def after_scenario(context, scenario):
    """Per-scenario teardown"""
    status_icon = "✅" if scenario.status == "passed" else "❌"
    console.print(
        f"[dim]{status_icon} {scenario.name} [{scenario.status}][/dim]"
    )


def before_tag(context, tag):
    """Tag-based setup"""
    if tag == "llm_generation":
        # Verify Ollama is available before LLM tests
        from llm_client import OllamaClient
        llm = OllamaClient()
        if not llm.check_connection():
            context.scenario.skip(
                "Skipping: Ollama not running. Start with: ollama serve"
            )
