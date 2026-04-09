"""
Artifact Migration Script
=========================
Handles data and config migrations when artifact contract versions change.

Usage:
    python scripts/migrate.py --check              # Check if migrations are needed
    python scripts/migrate.py --migrate             # Run all pending migrations
    python scripts/migrate.py --from 1.0 --to 1.1  # Migrate specific version range

Versioning rules (from SPEC_WORKFLOW.md):
  - Patch (1.0 -> 1.1): add optional fields only (backward compatible)
  - Minor (1.x -> 2.0): change required fields (requires migration)
  - Breaking changes require this script to convert old artifacts
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

# ── Migration Registry ───────────────────────────────────────────────────────
# Each migration is a function that transforms an artifact dict from one version
# to the next. Register new migrations here as contracts evolve.

MIGRATIONS: Dict[str, Dict[str, callable]] = {
    # Format: "artifact_type": {"from_version -> to_version": migration_function}
    #
    # Example (will be populated as contracts evolve):
    # "TestCaseArtifact": {
    #     "1.0 -> 1.1": migrate_tc_1_0_to_1_1,
    # },
}


# ── Migration Functions ──────────────────────────────────────────────────────
# Add concrete migration functions here as needed.

# def migrate_tc_1_0_to_1_1(artifact: dict) -> dict:
#     """Add optional 'automation_status' field introduced in 1.1."""
#     artifact.setdefault("automation_status", "not_automated")
#     artifact["schema_version"] = "1.1"
#     return artifact


# ── Engine ───────────────────────────────────────────────────────────────────


def get_current_versions() -> Dict[str, str]:
    """Return the current schema_version for each artifact type."""
    from stlc_platform.core.contracts import (
        APIModelArtifact,
        APITestArtifact,
        FeatureFileArtifact,
        PipelineRunArtifact,
        RequirementArtifact,
        SiteModelArtifact,
        StepDefinitionArtifact,
        TestCaseArtifact,
    )

    artifacts = [
        RequirementArtifact,
        TestCaseArtifact,
        FeatureFileArtifact,
        StepDefinitionArtifact,
        SiteModelArtifact,
        APIModelArtifact,
        APITestArtifact,
        PipelineRunArtifact,
    ]

    versions = {}
    for cls in artifacts:
        # Create minimal instance to read default schema_version
        try:
            # Get default from field
            version = cls.model_fields["schema_version"].default
            versions[cls.__name__] = version
        except (KeyError, AttributeError):
            versions[cls.__name__] = "unknown"

    return versions


def check_migrations_needed(artifact_dir: Optional[Path] = None) -> List[str]:
    """Check if any stored artifacts need migration. Returns list of issues."""
    issues = []
    current_versions = get_current_versions()

    if artifact_dir and artifact_dir.exists():
        for json_file in artifact_dir.glob("**/*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "schema_version" in data:
                    stored_version = data["schema_version"]
                    # Detect artifact type from keys
                    artifact_type = _detect_type(data)
                    if artifact_type:
                        expected = current_versions.get(artifact_type, "1.0")
                        if stored_version != expected:
                            issues.append(
                                f"{json_file}: {artifact_type} v{stored_version} "
                                f"-> v{expected} migration needed"
                            )
            except (json.JSONDecodeError, IOError):
                continue

    if not issues:
        issues.append("No migrations needed. All artifacts at current version.")

    return issues


def _detect_type(data: dict) -> Optional[str]:
    """Detect artifact type from its keys."""
    if "req_id" in data and "tc_id" not in data and "endpoint" not in data:
        return "RequirementArtifact"
    if "tc_id" in data:
        return "TestCaseArtifact"
    if "pipeline_name" in data:
        return "PipelineRunArtifact"
    if "endpoints" in data:
        return "APIModelArtifact"
    if "pages" in data and "base_url" in data:
        return "SiteModelArtifact"
    return None


def migrate_artifact(
    artifact: dict, artifact_type: str, from_version: str, to_version: str
) -> dict:
    """Apply a single migration to an artifact."""
    key = f"{from_version} -> {to_version}"
    type_migrations = MIGRATIONS.get(artifact_type, {})

    if key not in type_migrations:
        print(f"  No migration registered for {artifact_type} {key}")
        return artifact

    migrated = type_migrations[key](artifact)
    print(f"  Migrated {artifact_type} {key}")
    return migrated


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="STLC Platform Artifact Migration Tool")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if any migrations are needed (no changes made)",
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Run all pending migrations",
    )
    parser.add_argument(
        "--artifact-dir",
        type=str,
        default="./output",
        help="Directory containing artifact JSON files (default: ./output)",
    )
    parser.add_argument(
        "--versions",
        action="store_true",
        help="Print current artifact contract versions",
    )
    args = parser.parse_args()

    if args.versions:
        print("Current artifact contract versions:")
        for name, version in get_current_versions().items():
            print(f"  {name}: v{version}")
        return

    if args.check:
        print("Checking for pending migrations...")
        artifact_dir = Path(args.artifact_dir)
        issues = check_migrations_needed(artifact_dir)
        for issue in issues:
            print(f"  {issue}")
        return

    if args.migrate:
        print("Running migrations...")
        artifact_dir = Path(args.artifact_dir)
        issues = check_migrations_needed(artifact_dir)
        if any("migration needed" in i for i in issues):
            print("Migrations would be applied here (none registered yet).")
        else:
            print("No migrations needed.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
