"""
Requirements Reader (migrated)
==============================
Supports .txt, .pdf, .docx, .csv, .xlsx, .json, .md

Import path change:
  Old: from requirements_reader import RequirementsReader, Requirement
  New: from stlc_platform.agents.requirements_agent.reader import RequirementsReader, Requirement

The Requirement dataclass is also available as RequirementArtifact from contracts,
but this legacy class is kept for backward compatibility with the generator and
chroma_store which expect the dataclass interface.
"""

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from rich.console import Console

console = Console()


@dataclass
class Requirement:
    """Represents a single requirement."""

    req_id: str
    title: str
    description: str
    priority: str = "Medium"
    category: str = "Functional"
    acceptance_criteria: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "req_id": self.req_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "category": self.category,
            "acceptance_criteria": self.acceptance_criteria,
            "tags": self.tags,
        }

    def to_chroma_document(self) -> str:
        parts = [
            f"Requirement ID: {self.req_id}",
            f"Title: {self.title}",
            f"Description: {self.description}",
            f"Priority: {self.priority}",
            f"Category: {self.category}",
        ]
        if self.acceptance_criteria:
            parts.append("Acceptance Criteria:")
            for ac in self.acceptance_criteria:
                parts.append(f"  - {ac}")
        return "\n".join(parts)


class RequirementsReader:
    """Reads and parses requirements from various file formats."""

    SUPPORTED_FORMATS = {".txt", ".pdf", ".docx", ".csv", ".xlsx", ".json", ".md"}

    def read(self, file_path: str) -> List[Requirement]:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Requirements file not found: {file_path}")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {ext}. Supported: {self.SUPPORTED_FORMATS}")

        console.print(f"[cyan]Reading requirements from:[/cyan] {path.name}")

        readers = {
            ".txt": self._read_txt,
            ".md": self._read_txt,
            ".pdf": self._read_pdf,
            ".docx": self._read_docx,
            ".csv": self._read_csv,
            ".xlsx": self._read_xlsx,
            ".json": self._read_json,
        }

        requirements = readers[ext](str(path))
        console.print(f"[green]Loaded {len(requirements)} requirement(s)[/green]")
        return requirements

    def _read_txt(self, file_path: str) -> List[Requirement]:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        requirements = []
        blocks = self._split_into_blocks(content)

        if blocks:
            for i, block in enumerate(blocks):
                req = self._parse_text_block(block, i + 1)
                requirements.append(req)
        else:
            # A single textual requirement still needs the same structured
            # extraction (ID, title and acceptance criteria) as multi-block input.
            requirements.append(self._parse_text_block(content.strip(), 1))

        return requirements

    def _read_pdf(self, file_path: str) -> List[Requirement]:
        try:
            import PyPDF2
        except ImportError:
            raise ImportError("PyPDF2 not installed. Run: pip install PyPDF2")

        text_parts = []
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text_parts.append(page.extract_text())

        full_text = "\n".join(text_parts)
        return self._read_txt_from_string(full_text)

    def _read_docx(self, file_path: str) -> List[Requirement]:
        try:
            from docx import Document
        except ImportError:
            raise ImportError("python-docx not installed. Run: pip install python-docx")

        doc = Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        full_text = "\n".join(paragraphs)
        return self._read_txt_from_string(full_text)

    def _read_csv(self, file_path: str) -> List[Requirement]:
        requirements = []

        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                row_lower = {k.lower().strip(): v for k, v in row.items()}

                req_id = (
                    row_lower.get("id")
                    or row_lower.get("req_id")
                    or row_lower.get("requirement_id")
                    or f"REQ-{i + 1:03d}"
                )
                title = (
                    row_lower.get("title")
                    or row_lower.get("name")
                    or row_lower.get("summary")
                    or f"Requirement {i + 1}"
                )
                description = (
                    row_lower.get("description")
                    or row_lower.get("details")
                    or row_lower.get("content")
                    or row_lower.get("requirement")
                    or ""
                )
                priority = row_lower.get("priority", "Medium")
                category = row_lower.get("category") or row_lower.get("type", "Functional")
                ac_raw = row_lower.get("acceptance_criteria") or row_lower.get("ac") or ""
                acceptance_criteria = (
                    [ac.strip() for ac in ac_raw.split(";") if ac.strip()] if ac_raw else []
                )

                requirements.append(
                    Requirement(
                        req_id=str(req_id).strip(),
                        title=str(title).strip(),
                        description=str(description).strip(),
                        priority=str(priority).strip(),
                        category=str(category).strip(),
                        acceptance_criteria=acceptance_criteria,
                    )
                )

        return requirements

    def _read_xlsx(self, file_path: str) -> List[Requirement]:
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas not installed. Run: pip install pandas openpyxl")

        df = pd.read_excel(file_path)
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as tmp:
            df.to_csv(tmp.name, index=False)
            return self._read_csv(tmp.name)

    def _read_json(self, file_path: str) -> List[Requirement]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and "requirements" in data:
            items = data["requirements"]
        else:
            items = [data]

        requirements = []
        for i, item in enumerate(items):
            requirements.append(
                Requirement(
                    req_id=item.get("id", f"REQ-{i + 1:03d}"),
                    title=item.get("title", item.get("name", f"Requirement {i + 1}")),
                    description=item.get("description", item.get("details", "")),
                    priority=item.get("priority", "Medium"),
                    category=item.get("category", item.get("type", "Functional")),
                    acceptance_criteria=item.get("acceptance_criteria", []),
                    tags=item.get("tags", []),
                )
            )

        return requirements

    # ──────────────────────────── helpers ────────────────────────────

    def _read_txt_from_string(self, text: str) -> List[Requirement]:
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(text)
            return self._read_txt(tmp.name)

    def _split_into_blocks(self, content: str) -> List[str]:
        patterns = [
            r"\n(?=REQ-\d+)",
            r"\n(?=\d+\.\s)",
            r"\n(?=#{1,3}\s)",
            r"\n---+\n",
            r"\n===+\n",
        ]

        for pattern in patterns:
            blocks = re.split(pattern, content.strip())
            if len(blocks) > 1:
                return [b.strip() for b in blocks if b.strip()]

        return []

    def _parse_text_block(self, block: str, index: int) -> Requirement:
        lines = block.strip().split("\n")
        first_line = lines[0].strip()

        id_match = re.match(r"^(REQ-\d+|#\d+|\d+\.)\s*(.*)", first_line)
        if id_match:
            req_id = id_match.group(1).rstrip(".")
            title = id_match.group(2).strip().lstrip("#").strip()
        else:
            req_id = f"REQ-{index:03d}"
            title = first_line.lstrip("#").strip()

        description = "\n".join(lines[1:]).strip()

        ac = []
        ac_match = re.findall(
            r"(?:acceptance criteria|ac|given|when|then)[:\s]+(.+)",
            description,
            re.IGNORECASE,
        )
        for match in ac_match:
            ac.append(match.strip())

        return Requirement(
            req_id=req_id,
            title=title,
            description=description,
            acceptance_criteria=ac,
            raw_text=block,
        )
