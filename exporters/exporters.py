"""
Exporters - CSV and Zephyr Scale format output
"""
import csv
import json
import os
from datetime import datetime
from typing import List

from config import config
from rich.console import Console
from test_generator import TestCase

console = Console()


def _ensure_output_dir():
    os.makedirs(config.output.output_dir, exist_ok=True)


# ─────────────────────── Standard CSV Exporter ───────────────────────────────

class CSVExporter:
    """Export test cases to standard CSV format"""

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

    def export(self, test_cases: List[TestCase], filename: str = None) -> str:
        """Export test cases to CSV and return the file path"""
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

        console.print(f"[green]✅ CSV exported:[/green] {output_path}")
        return output_path

    def _format_steps(self, tc: TestCase) -> str:
        """Format steps as numbered list"""
        if not tc.steps:
            return ""
        parts = []
        for i, step in enumerate(tc.steps, 1):
            parts.append(f"{i}. {step.action} | Expected: {step.expected_result}")
        return "\n".join(parts)


# ─────────────────── Zephyr Scale CSV Exporter ───────────────────────────────

class ZephyrScaleExporter:
    """
    Export test cases in Zephyr Scale CSV import format.
    
    Zephyr Scale (for Jira) expects these columns for CSV import:
    https://support.smartbear.com/zephyr-scale-cloud/docs/test-management/importing-and-exporting-test-cases.html
    """

    # Zephyr Scale standard CSV column names
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

    def export(self, test_cases: List[TestCase], filename: str = None) -> str:
        """Export test cases in Zephyr Scale import format"""
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

        console.print(f"[green]✅ Zephyr Scale CSV exported:[/green] {output_path}")
        return output_path

    def _to_zephyr_row(self, tc: TestCase) -> dict:
        """Convert a TestCase to a Zephyr Scale CSV row"""

        # Priority mapping
        priority = self.PRIORITY_MAP.get(
            tc.priority.lower(), "Normal"
        )

        # Labels (tags + test type)
        labels_list = list(tc.tags) + [tc.test_type]
        if config.zephyr.default_labels:
            labels_list += config.zephyr.default_labels.split(",")
        labels = ", ".join(dict.fromkeys(labels_list))  # deduplicate

        # Folder path: e.g. "Generated Tests/REQ-001"
        folder = f"{config.zephyr.folder_prefix}/{tc.req_id}"

        # Step-by-step format (Zephyr expects: Step | Test Data | Expected Result)
        step_lines = []
        for i, step in enumerate(tc.steps, 1):
            step_lines.append(f"{step.action}\t\t{step.expected_result}")
        steps_formatted = "\n".join(step_lines)

        # Plain text script (Gherkin if available)
        if tc.given or tc.when or tc.then:
            plain_script = (
                f"Given {tc.given}\nWhen {tc.when}\nThen {tc.then}"
            ).strip()
        else:
            plain_script = tc.description

        # Estimated time in seconds
        try:
            est_seconds = int(float(tc.estimated_duration)) * 60
        except (ValueError, TypeError):
            est_seconds = 300  # 5 minutes default

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


# ─────────────────────── JSON Report Exporter ─────────────────────────────────

class JSONReportExporter:
    """Export generation metadata and summary as JSON"""

    def export(self, test_cases: List[TestCase], requirements_count: int) -> str:
        _ensure_output_dir()
        output_path = os.path.join(
            config.output.output_dir, config.output.report_filename
        )

        # Summary stats
        type_counts = {}
        priority_counts = {}
        req_counts = {}

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
                "avg_tests_per_requirement": round(
                    len(test_cases) / max(requirements_count, 1), 2
                ),
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

        console.print(f"[green]✅ JSON report saved:[/green] {output_path}")
        return output_path
