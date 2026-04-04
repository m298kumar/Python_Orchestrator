"""
Test Case Deduplicator
======================
Cross-requirement near-duplicate detection using TF-IDF cosine similarity.

Compares all test case pairs and removes near-duplicates, keeping the one
with the higher quality_score. No external dependencies (scikit-learn etc.)
— TF-IDF vectors are represented as plain dicts (sparse vectors).
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from stlc_platform.core.contracts import TestCaseArtifact

logger = logging.getLogger(__name__)


@dataclass
class DeduplicationResult:
    """Result of a deduplication pass."""

    kept: List[TestCaseArtifact] = field(default_factory=list)
    removed: List[TestCaseArtifact] = field(default_factory=list)
    duplicate_pairs: List[Tuple[str, str, float]] = field(default_factory=list)


class TestCaseDeduplicator:
    """Remove near-duplicate test cases using TF-IDF cosine similarity."""

    def __init__(self, threshold: float = 0.85):
        self._threshold = threshold

    # ── Public API ────────────────────────────────────────────────────────────

    def deduplicate(self, test_cases: List[TestCaseArtifact]) -> DeduplicationResult:
        """Remove near-duplicate TCs using TF-IDF cosine similarity.

        For each duplicate pair, keeps the TC with higher quality_score.
        If scores are equal, keeps the first one (by list position).
        """
        if len(test_cases) <= 1:
            return DeduplicationResult(kept=list(test_cases))

        # Extract text and build TF-IDF vectors
        documents = [self._extract_text(tc) for tc in test_cases]
        vectors = self._build_tfidf_vectors(documents)

        # Track which indices have been marked for removal
        removed_indices: Set[int] = set()
        duplicate_pairs: List[Tuple[str, str, float]] = []

        # Compare all pairs
        n = len(test_cases)
        for i in range(n):
            if i in removed_indices:
                continue
            for j in range(i + 1, n):
                if j in removed_indices:
                    continue
                sim = self._cosine_similarity(vectors[i], vectors[j])
                if sim >= self._threshold:
                    duplicate_pairs.append(
                        (test_cases[i].tc_id, test_cases[j].tc_id, round(sim, 4))
                    )
                    # Keep TC with higher quality_score; on tie keep earlier one
                    score_i = getattr(test_cases[i], "quality_score", 0.0)
                    score_j = getattr(test_cases[j], "quality_score", 0.0)
                    if score_j > score_i:
                        removed_indices.add(i)
                        break  # i is removed, no need to compare further
                    else:
                        removed_indices.add(j)

        kept = [tc for idx, tc in enumerate(test_cases) if idx not in removed_indices]
        removed = [tc for idx, tc in enumerate(test_cases) if idx in removed_indices]

        if removed:
            logger.info(
                "Deduplication: %d kept, %d removed, %d duplicate pairs",
                len(kept),
                len(removed),
                len(duplicate_pairs),
            )

        return DeduplicationResult(
            kept=kept,
            removed=removed,
            duplicate_pairs=duplicate_pairs,
        )

    # ── TF-IDF ────────────────────────────────────────────────────────────────

    def _build_tfidf_vectors(
        self, documents: List[str]
    ) -> List[Dict[str, float]]:
        """Build TF-IDF vectors from document texts.

        Returns a list of sparse vectors (one dict per document).
        Keys are terms, values are TF-IDF weights.
        """
        n = len(documents)
        if n == 0:
            return []

        # Tokenize all documents
        tokenized = [self._tokenize(doc) for doc in documents]

        # Document frequency: how many documents contain each term
        df: Dict[str, int] = {}
        for tokens in tokenized:
            unique_terms = set(tokens)
            for term in unique_terms:
                df[term] = df.get(term, 0) + 1

        # Build TF-IDF vector for each document
        vectors: List[Dict[str, float]] = []
        for tokens in tokenized:
            if not tokens:
                vectors.append({})
                continue

            total = len(tokens)
            # Term frequency
            tf: Dict[str, float] = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1

            # TF-IDF (smoothed IDF to handle terms present in all documents)
            vec: Dict[str, float] = {}
            for term, count in tf.items():
                term_freq = count / total
                idf = math.log((1 + n) / (1 + df[term])) + 1.0
                weight = term_freq * idf
                if weight > 0:
                    vec[term] = weight

            vectors.append(vec)

        return vectors

    # ── Text extraction ───────────────────────────────────────────────────────

    def _extract_text(self, tc: TestCaseArtifact) -> str:
        """Extract all meaningful text from a test case for comparison."""
        parts = [
            tc.title or "",
            tc.description or "",
            tc.given or "",
            tc.when or "",
            tc.then or "",
        ]
        for step in tc.steps:
            parts.append(step.action or "")
            parts.append(step.expected_result or "")
        return " ".join(parts)

    # ── Cosine similarity ─────────────────────────────────────────────────────

    @staticmethod
    def _cosine_similarity(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
        """Compute cosine similarity between two sparse vectors."""
        if not vec_a or not vec_b:
            return 0.0

        # Dot product (iterate over the smaller vector for efficiency)
        if len(vec_a) > len(vec_b):
            vec_a, vec_b = vec_b, vec_a

        dot = 0.0
        for term, weight_a in vec_a.items():
            if term in vec_b:
                dot += weight_a * vec_b[term]

        if dot == 0.0:
            return 0.0

        mag_a = math.sqrt(sum(w * w for w in vec_a.values()))
        mag_b = math.sqrt(sum(w * w for w in vec_b.values()))

        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0

        return dot / (mag_a * mag_b)

    # ── Tokenizer ─────────────────────────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple whitespace tokenizer with minimum length filter."""
        return [w for w in re.findall(r"[a-z0-9]{3,}", text.lower()) if len(w) >= 3]
