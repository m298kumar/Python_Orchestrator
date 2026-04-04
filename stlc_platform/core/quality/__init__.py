"""
Quality Scoring
===============
Test case quality assessment and gating for autonomous self-improvement.
"""

from stlc_platform.core.quality.deduplicator import DeduplicationResult, TestCaseDeduplicator
from stlc_platform.core.quality.scorer import QualityReport, TestCaseScorer

__all__ = ["DeduplicationResult", "QualityReport", "TestCaseDeduplicator", "TestCaseScorer"]
