from pathlib import Path

import pytest
from stlc_platform.core.specifications import SpecificationLoader


def _write_spec(path: Path, status: str = "Approved") -> None:
    path.write_text(
        "# Spec\n\n"
        "**Specification ID:** STLC-TEST-001  \n"
        "**Version:** 1.2.3  \n"
        f"**Status:** {status}  \n",
        encoding="utf-8",
    )


def test_loads_approved_versioned_specification(tmp_path):
    path = tmp_path / "spec.md"
    _write_spec(path)
    loader = SpecificationLoader(
        {"specifications": {"enforce": True, "requirements": str(path)}}
    )

    spec = loader.load("requirements")

    assert spec.specification_id == "STLC-TEST-001"
    assert spec.version == "1.2.3"


def test_enforcement_rejects_unapproved_specification(tmp_path):
    path = tmp_path / "spec.md"
    _write_spec(path, status="Draft")
    loader = SpecificationLoader(
        {"specifications": {"enforce": True, "requirements": str(path)}}
    )

    with pytest.raises(ValueError, match="not approved"):
        loader.load("requirements")
