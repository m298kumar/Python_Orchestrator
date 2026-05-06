"""
Exporters (migrated)
====================
CSV, Zephyr Scale, and JSON Report export.

Import path change:
  Old: from exporters.exporters import CSVExporter, ZephyrScaleExporter, JSONReportExporter
  New: from stlc_platform.exporters import CSVExporter, ZephyrScaleExporter, JSONReportExporter

These exporters accept objects with the same attributes as TestCase dataclass.
They work with both the old TestCase dataclass and the new TestCaseArtifact Pydantic model.
"""

import csv
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

from rich.console import Console

from stlc_platform.core.config_loader import config

console = Console()


def _ensure_output_dir():
    os.makedirs(config.output.output_dir, exist_ok=True)


class CSVExporter:
    """Export test cases to standard CSV format."""

    HEADERS = [
        "TC ID",
        "Requirement ID",
        "Title",
        "Description",
        "Preconditions",
        "Test Type",
        "Priority",
        "Category",
        "Component",
        "Steps",
        "Expected Outcome",
        "Given",
        "When",
        "Then",
        "Tags",
        "Estimated Duration (min)",
        "Generated At",
    ]

    def export(self, test_cases: List, filename: Optional[str] = None) -> str:
        _ensure_output_dir()
        output_path = os.path.join(
            config.output.output_dir,
            filename or config.output.csv_filename,
        )

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.HEADERS)
            writer.writeheader()

            for tc in test_cases:
                steps_text = self._format_steps(tc)
                writer.writerow(
                    {
                        "TC ID": tc.tc_id,
                        "Requirement ID": tc.req_id,
                        "Title": tc.title,
                        "Description": tc.description,
                        "Preconditions": tc.preconditions,
                        "Test Type": tc.test_type,
                        "Priority": tc.priority,
                        "Category": tc.category,
                        "Component": tc.component,
                        "Steps": steps_text,
                        "Expected Outcome": tc.expected_outcome,
                        "Given": tc.given,
                        "When": tc.when,
                        "Then": tc.then,
                        "Tags": ", ".join(tc.tags),
                        "Estimated Duration (min)": tc.estimated_duration,
                        "Generated At": datetime.now().isoformat(),
                    }
                )

        console.print(f"[green]CSV exported:[/green] {output_path}")
        return output_path

    def _format_steps(self, tc) -> str:
        if not tc.steps:
            return ""
        parts = []
        for i, step in enumerate(tc.steps, 1):
            parts.append(f"{i}. {step.action} | Expected: {step.expected_result}")
        return "\n".join(parts)


class ZephyrScaleExporter:
    """Export test cases in Zephyr Scale CSV import format."""

    HEADERS = [
        "Name",
        "Status",
        "Priority",
        "Component",
        "Labels",
        "Description",
        "Precondition",
        "Test Script (Step-by-Step)",
        "Test Script (Plain Text)",
        "Folder",
        "Requirement",
        "Estimated Time (s)",
        "Owner",
    ]

    PRIORITY_MAP = {
        "high": "High",
        "medium": "Normal",
        "normal": "Normal",
        "low": "Low",
        "critical": "High",
    }

    def export(self, test_cases: List, filename: Optional[str] = None) -> str:
        _ensure_output_dir()
        output_path = os.path.join(
            config.output.output_dir,
            filename or config.output.zephyr_filename,
        )

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.HEADERS, quoting=csv.QUOTE_ALL)
            writer.writeheader()

            for tc in test_cases:
                writer.writerow(self._to_zephyr_row(tc))

        console.print(f"[green]Zephyr Scale CSV exported:[/green] {output_path}")
        return output_path

    def _to_zephyr_row(self, tc) -> dict:
        priority = self.PRIORITY_MAP.get(tc.priority.lower(), "Normal")

        labels_list = list(tc.tags) + [tc.test_type]
        if config.zephyr.default_labels:
            labels_list += config.zephyr.default_labels.split(",")
        labels = ", ".join(dict.fromkeys(labels_list))

        folder = f"{config.zephyr.folder_prefix}/{tc.req_id}"

        step_lines = []
        for step in tc.steps:
            step_lines.append(f"{step.action}\t\t{step.expected_result}")
        steps_formatted = "\n".join(step_lines)

        if tc.given or tc.when or tc.then:
            plain_script = (f"Given {tc.given}\nWhen {tc.when}\nThen {tc.then}").strip()
        else:
            plain_script = tc.description

        try:
            est_seconds = int(float(tc.estimated_duration)) * 60
        except (ValueError, TypeError):
            est_seconds = 300

        return {
            "Name": tc.title,
            "Status": config.zephyr.default_status,
            "Priority": priority,
            "Component": tc.component or config.zephyr.default_component,
            "Labels": labels,
            "Description": tc.description,
            "Precondition": tc.preconditions,
            "Test Script (Step-by-Step)": steps_formatted,
            "Test Script (Plain Text)": plain_script,
            "Folder": folder,
            "Requirement": tc.req_id,
            "Estimated Time (s)": str(est_seconds),
            "Owner": "",
        }


class JSONReportExporter:
    """Export generation metadata and summary as JSON."""

    def export(self, test_cases: List, requirements_count: int) -> str:
        _ensure_output_dir()
        output_path = os.path.join(config.output.output_dir, config.output.report_filename)

        type_counts: Dict[str, int] = {}
        priority_counts: Dict[str, int] = {}
        req_counts: Dict[str, int] = {}

        for tc in test_cases:
            type_counts[tc.test_type] = type_counts.get(tc.test_type, 0) + 1
            priority_counts[tc.priority] = priority_counts.get(tc.priority, 0) + 1
            req_counts[tc.req_id] = req_counts.get(tc.req_id, 0) + 1

        report = {
            "generated_at": datetime.now().isoformat(),
            "model_used": config.ollama.model,
            "summary": {
                "total_requirements": requirements_count,
                "total_test_cases": len(test_cases),
                "avg_tests_per_requirement": round(len(test_cases) / max(requirements_count, 1), 2),
            },
            "breakdown_by_type": type_counts,
            "breakdown_by_priority": priority_counts,
            "test_cases_per_requirement": req_counts,
            "test_cases": [
                {
                    "tc_id": tc.tc_id,
                    "req_id": tc.req_id,
                    "title": tc.title,
                    "test_type": tc.test_type,
                    "priority": tc.priority,
                    "steps_count": len(tc.steps),
                }
                for tc in test_cases
            ],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        console.print(f"[green]JSON report saved:[/green] {output_path}")
        return output_path
