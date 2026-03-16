"""
Shared test fixtures for the STLC Platform test suite.
"""

import os
import sys
import tempfile
import shutil

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def temp_output_dir():
    """Provide a temporary output directory, cleaned up after test."""
    d = tempfile.mkdtemp(prefix="stlc_test_output_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def temp_chroma_dir():
    """Provide a temporary ChromaDB directory, cleaned up after test."""
    d = tempfile.mkdtemp(prefix="stlc_test_chroma_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_requirement():
    """Return a sample Requirement dataclass instance."""
    from stlc_platform.agents.requirements_agent.reader import Requirement
    return Requirement(
        req_id="REQ-001",
        title="User Login Authentication",
        description="Users must be able to log in with valid username and password",
        priority="High",
        category="Authentication",
        acceptance_criteria=[
            "User can log in with valid credentials",
            "Invalid credentials show error message",
            "Account locks after 5 failed attempts",
        ],
        tags=["login", "security"],
    )


@pytest.fixture
def sample_test_case():
    """Return a sample TestCase-like object for export tests."""
    from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact
    return TestCaseArtifact(
        tc_id="TC-0001",
        req_id="REQ-001",
        title="Verify user can log in with valid credentials",
        description="Test that valid username and password combination grants access",
        preconditions="User account exists with known credentials",
        test_type="positive",
        priority="High",
        steps=[
            TestStepArtifact(
                action="Navigate to the login page",
                expected_result="Login form is displayed with username and password fields",
            ),
            TestStepArtifact(
                action="Enter valid username 'testuser' in the username field",
                expected_result="Username field shows 'testuser'",
            ),
            TestStepArtifact(
                action="Enter valid password and click the Sign In button",
                expected_result="Dashboard page loads with welcome message",
            ),
        ],
        expected_outcome="User is authenticated and redirected to the dashboard",
        tags=["login", "positive", "authentication"],
        category="Authentication",
        component="Login Screen",
        given="a registered user with valid credentials",
        when="the user enters their username and password and clicks Sign In",
        then="the user is redirected to the dashboard with a welcome message",
        estimated_duration="3",
    )
