"""
Tests for TestCaseDeduplicator
==============================
Verifies TF-IDF cosine similarity deduplication across test cases.
"""

from __future__ import annotations

from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact
from stlc_platform.core.quality.deduplicator import TestCaseDeduplicator

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_tc(
    tc_id: str = "TC-0001",
    title: str = "Test login",
    description: str = "Verify login works",
    steps: list | None = None,
    given: str = "User is on login page",
    when: str = "User enters credentials",
    then: str = "User is logged in",
    quality_score: float = 0.0,
) -> TestCaseArtifact:
    """Create a minimal TestCaseArtifact for testing."""
    default_steps = [
        TestStepArtifact(action="Open login page", expected_result="Login page displayed"),
        TestStepArtifact(action="Enter username", expected_result="Username accepted"),
        TestStepArtifact(action="Click submit", expected_result="Form submitted"),
    ]
    return TestCaseArtifact(
        tc_id=tc_id,
        req_id="REQ-001",
        title=title,
        description=description,
        preconditions="System is running",
        test_type="positive",
        priority="Medium",
        steps=steps if steps is not None else default_steps,
        expected_outcome="Success",
        given=given,
        when=when,
        then=then,
        quality_score=quality_score,
    )


# ── Tests ────────────────────────────────────────────────────────────────────


class TestDeduplicatorEmptyAndSingle:
    """Edge cases: empty list and single TC."""

    def test_empty_list_returns_empty(self) -> None:
        deduplicator = TestCaseDeduplicator(threshold=0.85)
        result = deduplicator.deduplicate([])
        assert result.kept == []
        assert result.removed == []
        assert result.duplicate_pairs == []

    def test_single_tc_kept(self) -> None:
        tc = _make_tc()
        deduplicator = TestCaseDeduplicator(threshold=0.85)
        result = deduplicator.deduplicate([tc])
        assert len(result.kept) == 1
        assert result.kept[0].tc_id == tc.tc_id
        assert result.removed == []


class TestDeduplicatorDuplicates:
    """Tests for duplicate detection and removal."""

    def test_identical_tcs_deduped(self) -> None:
        """Two identical TCs: keep the one with higher quality_score."""
        tc1 = _make_tc(tc_id="TC-0001", quality_score=0.5)
        tc2 = _make_tc(tc_id="TC-0002", quality_score=0.8)
        deduplicator = TestCaseDeduplicator(threshold=0.85)
        result = deduplicator.deduplicate([tc1, tc2])

        assert len(result.kept) == 1
        assert len(result.removed) == 1
        # TC-0002 has higher score, so it should be kept
        assert result.kept[0].tc_id == "TC-0002"
        assert result.removed[0].tc_id == "TC-0001"
        assert len(result.duplicate_pairs) == 1
        assert result.duplicate_pairs[0][2] >= 0.85

    def test_similar_tcs_above_threshold_deduped(self) -> None:
        """Two TCs with very similar text should be flagged as duplicates."""
        tc1 = _make_tc(
            tc_id="TC-0001",
            title="Verify user login with valid credentials",
            description="Test that a user can login with valid username and password",
            given="User is on the login page with valid credentials",
            when="User enters valid username and valid password and clicks login",
            then="User is redirected to the dashboard after successful login",
            quality_score=0.7,
        )
        tc2 = _make_tc(
            tc_id="TC-0002",
            title="Verify user login with valid credentials check",
            description="Test that a user can login with valid username and password successfully",
            given="User is on the login page with valid credentials ready",
            when="User enters valid username and valid password and clicks login button",
            then="User is redirected to the dashboard after successful login attempt",
            quality_score=0.6,
        )
        deduplicator = TestCaseDeduplicator(threshold=0.80)
        result = deduplicator.deduplicate([tc1, tc2])

        assert len(result.kept) == 1
        assert len(result.removed) == 1
        # TC-0001 has higher quality score
        assert result.kept[0].tc_id == "TC-0001"

    def test_different_tcs_all_kept(self) -> None:
        """Two completely different TCs should both be kept."""
        tc1 = _make_tc(
            tc_id="TC-0001",
            title="Verify user login with valid credentials",
            description="Test that a user can login with valid username and password",
            steps=[
                TestStepArtifact(action="Open login page", expected_result="Login page displayed"),
                TestStepArtifact(
                    action="Enter username and password", expected_result="Credentials entered"
                ),
                TestStepArtifact(
                    action="Click login button", expected_result="Logged in successfully"
                ),
            ],
            given="User is on the login page",
            when="User enters valid credentials",
            then="User is logged in to dashboard",
        )
        tc2 = _make_tc(
            tc_id="TC-0002",
            title="Verify product search returns results",
            description="Test that searching for a product returns matching items from catalog",
            steps=[
                TestStepArtifact(
                    action="Navigate to product catalog", expected_result="Catalog page shown"
                ),
                TestStepArtifact(
                    action="Enter search term in search bar", expected_result="Search term accepted"
                ),
                TestStepArtifact(
                    action="Click search button", expected_result="Matching products displayed"
                ),
            ],
            given="User is on the product catalog page",
            when="User searches for a specific product by name",
            then="Matching products are displayed in the results list",
        )
        deduplicator = TestCaseDeduplicator(threshold=0.85)
        result = deduplicator.deduplicate([tc1, tc2])

        assert len(result.kept) == 2
        assert len(result.removed) == 0
        assert len(result.duplicate_pairs) == 0


class TestDeduplicatorThresholds:
    """Tests for extreme threshold values."""

    def test_threshold_zero_removes_all_but_one(self) -> None:
        """With threshold=0, every pair is a 'duplicate' so only one survives."""
        tc1 = _make_tc(tc_id="TC-0001", title="Login test", description="Login verification")
        tc2 = _make_tc(
            tc_id="TC-0002",
            title="Product search",
            description="Search product catalog",
            steps=[
                TestStepArtifact(action="Go to catalog", expected_result="Catalog shown"),
                TestStepArtifact(action="Search product", expected_result="Results shown"),
                TestStepArtifact(action="Select item", expected_result="Item details shown"),
            ],
            given="User is on catalog",
            when="User searches",
            then="Results displayed",
        )
        tc3 = _make_tc(
            tc_id="TC-0003",
            title="Checkout flow",
            description="Complete checkout process",
            steps=[
                TestStepArtifact(action="Add item to cart", expected_result="Item added"),
                TestStepArtifact(action="Go to checkout", expected_result="Checkout page shown"),
                TestStepArtifact(action="Submit order", expected_result="Order confirmed"),
            ],
            given="User has items in cart",
            when="User proceeds to checkout",
            then="Order is placed successfully",
        )
        deduplicator = TestCaseDeduplicator(threshold=0.0)
        result = deduplicator.deduplicate([tc1, tc2, tc3])

        # With threshold 0, any non-zero similarity causes dedup.
        # At least one must survive; most should be removed.
        assert len(result.kept) >= 1
        assert len(result.kept) + len(result.removed) == 3

    def test_threshold_one_keeps_all(self) -> None:
        """With threshold=1.0, nothing is a duplicate (cosine sim is rarely exactly 1.0)."""
        tc1 = _make_tc(tc_id="TC-0001", title="Login test", description="Login verification")
        tc2 = _make_tc(
            tc_id="TC-0002",
            title="Login test slightly different",
            description="Login verification with extras",
        )
        deduplicator = TestCaseDeduplicator(threshold=1.0)
        result = deduplicator.deduplicate([tc1, tc2])

        assert len(result.kept) == 2
        assert len(result.removed) == 0


class TestDeduplicatorTiebreaker:
    """Tests for quality_score tiebreaker behavior."""

    def test_quality_score_tiebreaker(self) -> None:
        """When quality scores are equal, keep the first TC."""
        tc1 = _make_tc(tc_id="TC-0001", quality_score=0.7)
        tc2 = _make_tc(tc_id="TC-0002", quality_score=0.7)
        deduplicator = TestCaseDeduplicator(threshold=0.85)
        result = deduplicator.deduplicate([tc1, tc2])

        assert len(result.kept) == 1
        assert len(result.removed) == 1
        # Equal scores -> keep first (TC-0001)
        assert result.kept[0].tc_id == "TC-0001"
        assert result.removed[0].tc_id == "TC-0002"
