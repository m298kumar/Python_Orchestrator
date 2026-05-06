"""Tests for POM Generator."""

import pytest
from stlc_platform.agents.bdd_agent.pom_generator import PageObjectStub, POMGenerator
from stlc_platform.core.contracts import (
    CrawledPageArtifact,
    PageElementArtifact,
    TestCaseArtifact,
)


@pytest.fixture
def pom_gen():
    return POMGenerator(language="python", automation_lib="playwright")


@pytest.fixture
def java_pom_gen():
    return POMGenerator(language="java", automation_lib="selenium")


def _make_test_cases():
    return [
        TestCaseArtifact(
            tc_id="TC-001",
            req_id="REQ-001",
            title="User can login",
            description="Verify login",
            preconditions="User on login page",
            test_type="functional",
            priority="High",
            component="Login Page",
            given="the user is on the login page",
            when="the user enters 'admin' in 'username' and clicks 'Submit' button",
            then="the dashboard is displayed",
        ),
        TestCaseArtifact(
            tc_id="TC-002",
            req_id="REQ-001",
            title="User sees error on invalid login",
            description="Verify error message",
            preconditions="User on login page",
            test_type="functional",
            priority="High",
            component="Login Page",
            given="the user is on the login page",
            when="the user enters 'wrong' in 'password' and clicks 'Submit' button",
            then="an error message is displayed",
        ),
        TestCaseArtifact(
            tc_id="TC-003",
            req_id="REQ-002",
            title="User can search products",
            description="Verify search",
            preconditions="User on dashboard",
            test_type="functional",
            priority="Medium",
            component="Dashboard",
            given="the user is on the dashboard",
            when="the user enters 'laptop' in the search field",
            then="search results are displayed",
        ),
    ]


def _make_crawled_pages():
    return [
        CrawledPageArtifact(
            url="/login",
            title="Login",
            elements=[
                PageElementArtifact(
                    element_type="input",
                    name="username",
                    selector="#username",
                    text="",
                ),
                PageElementArtifact(
                    element_type="input",
                    name="password",
                    selector="#password",
                    text="",
                ),
                PageElementArtifact(
                    element_type="button",
                    name="submit",
                    selector='[data-testid="login-btn"]',
                    text="Submit",
                ),
            ],
        ),
    ]


class TestPOMExtraction:
    def test_extracts_pages_from_components(self, pom_gen):
        tcs = _make_test_cases()
        result = pom_gen.generate(tcs)
        # Should have 2 pages: LoginPage and DashboardPage
        assert len(result) >= 2
        class_names = [r.class_name for r in result]
        assert "LoginPage" in class_names
        assert "DashboardPage" in class_names

    def test_generates_python_pom(self, pom_gen):
        tcs = _make_test_cases()
        result = pom_gen.generate(tcs)
        assert all(isinstance(r, PageObjectStub) for r in result)
        assert all(r.language == "python" for r in result)

    def test_pom_has_class_definition(self, pom_gen):
        tcs = _make_test_cases()
        result = pom_gen.generate(tcs)
        login_pom = next(r for r in result if r.class_name == "LoginPage")
        assert "class LoginPage" in login_pom.content

    def test_pom_has_locators(self, pom_gen):
        tcs = _make_test_cases()
        result = pom_gen.generate(tcs)
        login_pom = next(r for r in result if r.class_name == "LoginPage")
        assert login_pom.locator_count > 0

    def test_pom_has_actions(self, pom_gen):
        tcs = _make_test_cases()
        result = pom_gen.generate(tcs)
        login_pom = next(r for r in result if r.class_name == "LoginPage")
        assert login_pom.action_count > 0

    def test_pom_has_navigate_method(self, pom_gen):
        tcs = _make_test_cases()
        result = pom_gen.generate(tcs)
        login_pom = next(r for r in result if r.class_name == "LoginPage")
        assert "def navigate" in login_pom.content

    def test_pom_has_todo_selectors_by_default(self, pom_gen):
        tcs = _make_test_cases()
        result = pom_gen.generate(tcs)
        login_pom = next(r for r in result if r.class_name == "LoginPage")
        assert "TODO" in login_pom.content

    def test_filename_is_snake_case(self, pom_gen):
        tcs = _make_test_cases()
        result = pom_gen.generate(tcs)
        login_pom = next(r for r in result if r.class_name == "LoginPage")
        assert login_pom.filename == "login_page.py"


class TestPOMWithCrawledSelectors:
    def test_merges_real_selectors(self, pom_gen):
        tcs = _make_test_cases()
        crawled = _make_crawled_pages()
        result = pom_gen.generate(tcs, crawled_pages=crawled)
        login_pom = next(r for r in result if r.class_name == "LoginPage")
        # Should contain real selectors from crawled data
        content = login_pom.content
        # At least some selectors should be real (not TODO)
        assert "#username" in content or "#password" in content or "login-btn" in content


class TestJavaPOM:
    def test_generates_java_pom(self, java_pom_gen):
        tcs = _make_test_cases()
        result = java_pom_gen.generate(tcs)
        assert all(r.language == "java" for r in result)

    def test_java_pom_has_class(self, java_pom_gen):
        tcs = _make_test_cases()
        result = java_pom_gen.generate(tcs)
        login_pom = next(r for r in result if r.class_name == "LoginPage")
        assert "public class LoginPage" in login_pom.content

    def test_java_pom_has_selenium_imports(self, java_pom_gen):
        tcs = _make_test_cases()
        result = java_pom_gen.generate(tcs)
        login_pom = next(r for r in result if r.class_name == "LoginPage")
        assert "import org.openqa.selenium" in login_pom.content

    def test_java_filename(self, java_pom_gen):
        tcs = _make_test_cases()
        result = java_pom_gen.generate(tcs)
        login_pom = next(r for r in result if r.class_name == "LoginPage")
        assert login_pom.filename.endswith(".java")


class TestPOMEdgeCases:
    def test_unsupported_language_raises(self):
        with pytest.raises(ValueError, match="Unsupported language"):
            POMGenerator(language="ruby")

    def test_empty_component_infers_page(self, pom_gen):
        tcs = [
            TestCaseArtifact(
                tc_id="TC-X",
                req_id="REQ-X",
                title="User on checkout page does something",
                description="Checkout flow",
                preconditions="",
                test_type="functional",
                priority="Medium",
                component="",  # empty
                given="user is on checkout page",
                when="user clicks pay",
                then="order is confirmed",
            ),
        ]
        result = pom_gen.generate(tcs)
        assert len(result) >= 1
        # Should infer "Checkout" from title containing "checkout page"
        class_names = [r.class_name for r in result]
        assert any("Checkout" in cn for cn in class_names) or any(
            "Base" in cn for cn in class_names
        )

    def test_no_test_cases_returns_empty(self, pom_gen):
        result = pom_gen.generate([])
        assert result == []
