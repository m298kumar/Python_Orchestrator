"""
Step definitions for Test Case Generation Orchestrator
"""
import os
import csv
import json
import tempfile
from behave import given, when, then
from unittest.mock import MagicMock, patch

from requirements_reader import Requirement, RequirementsReader
from test_generator import TestCase, TestStep, TestCaseGenerator
from chroma_store import RequirementsVectorStore
from exporters.exporters import CSVExporter, ZephyrScaleExporter, JSONReportExporter
from llm_client import OllamaClient


# ─────────────────────────── GIVEN STEPS ──────────────────────────────────────

@given('the Ollama LLM server is running with model "{model}"')
def step_ollama_running(context, model):
    from config import config
    config.ollama.model = model
    context.llm_client = OllamaClient()
    # In tests, we mock unless explicitly running integration tests
    if not context.llm_client.check_connection():
        context.llm_client = _create_mock_llm()


@given('the ChromaDB vector store is initialized')
def step_chroma_initialized(context):
    context.vector_store = RequirementsVectorStore()


@given('I have a requirements file "{file_type}" at "{file_path}"')
def step_requirements_file(context, file_type, file_path):
    # Create test data files if they don't exist
    test_data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "test_data"
    )
    os.makedirs(test_data_dir, exist_ok=True)

    full_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        file_path,
    )

    if not os.path.exists(full_path):
        _create_sample_file(full_path, file_type)

    context.requirements_file_path = full_path
    context.requirements_file_type = file_type


@given('I have a requirement with ID "{req_id}"')
def step_requirement_id(context, req_id):
    context.current_requirement = Requirement(
        req_id=req_id,
        title="",
        description="",
    )


@given('the requirement title is "{title}"')
def step_requirement_title(context, title):
    context.current_requirement.title = title


@given('the requirement description is "{description}"')
def step_requirement_description(context, description):
    context.current_requirement.description = description


@given('test generation is configured with negative tests enabled')
def step_enable_negative_tests(context):
    from config import config
    config.include_negative_tests = True
    config.include_edge_cases = True


@given('I have the following requirements')
def step_requirements_table(context):
    context.current_requirements = []
    for row in context.table:
        context.current_requirements.append(
            Requirement(
                req_id=row["req_id"],
                title=row["title"],
                description=row["description"],
            )
        )


@given('I have 3 generated test cases for "{req_id}"')
def step_have_test_cases(context, req_id):
    context.generated_test_cases = [
        TestCase(
            tc_id=f"TC-{i:04d}",
            req_id=req_id,
            title=f"Test Case {i} for {req_id}",
            description=f"Description for test case {i}",
            preconditions="System is up",
            test_type=["positive", "negative", "edge_case"][i % 3],
            priority="Medium",
            steps=[
                TestStep(action=f"Step {j}", expected_result=f"Result {j}")
                for j in range(1, 3)
            ],
            expected_outcome=f"Expected outcome {i}",
            tags=["automated"],
            given="the system is ready",
            when="user performs the action",
            then="the expected result occurs",
        )
        for i in range(1, 4)
    ]


@given('I have a requirements CSV file with {count:d} requirements')
def step_requirements_csv(context, count):
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    )
    writer = csv.writer(tmp)
    writer.writerow(["id", "title", "description", "priority"])
    for i in range(1, count + 1):
        writer.writerow([
            f"REQ-{i:03d}",
            f"Requirement {i} Title",
            f"Description for requirement number {i}",
            "Medium",
        ])
    tmp.close()
    context.requirements_file_path = tmp.name


# ─────────────────────────── WHEN STEPS ───────────────────────────────────────

@when('I read the requirements file')
def step_read_requirements(context):
    reader = RequirementsReader()
    context.current_requirements = reader.read(context.requirements_file_path)


@when('I generate test cases for the requirement')
def step_generate_test_cases(context):
    llm = getattr(context, "llm_client", None) or _create_mock_llm()
    vector_store = getattr(context, "vector_store", None)
    generator = TestCaseGenerator(llm_client=llm, vector_store=vector_store)
    context.generated_test_cases = generator.generate_for_requirement(
        context.current_requirement
    )


@when('I add all requirements to the vector store')
def step_add_to_vector_store(context):
    context.vector_store.add_requirements(context.current_requirements)


@when('I search for requirements similar to "{query}"')
def step_search_similar(context, query):
    context.search_results = context.vector_store.search_similar(query, n_results=5)


@when('I export the test cases to CSV format')
def step_export_csv(context):
    exporter = CSVExporter()
    context.csv_output_path = exporter.export(context.generated_test_cases)


@when('I export the test cases to Zephyr Scale format')
def step_export_zephyr(context):
    exporter = ZephyrScaleExporter()
    context.zephyr_output_path = exporter.export(context.generated_test_cases)


@when('I run the full orchestration pipeline')
def step_run_pipeline(context):
    reader = RequirementsReader()
    reqs = reader.read(context.requirements_file_path)
    context.current_requirements = reqs

    llm = _create_mock_llm()
    generator = TestCaseGenerator(llm_client=llm, vector_store=None)
    context.generated_test_cases = generator.generate_for_all(reqs)

    CSVExporter().export(context.generated_test_cases)
    ZephyrScaleExporter().export(context.generated_test_cases)
    context.report_path = JSONReportExporter().export(
        context.generated_test_cases, len(reqs)
    )


# ─────────────────────────── THEN STEPS ───────────────────────────────────────

@then('I should get at least {count:d} requirement')
def step_check_requirement_count(context, count):
    assert len(context.current_requirements) >= count, (
        f"Expected at least {count} requirement(s), got {len(context.current_requirements)}"
    )


@then('each requirement should have an ID and title')
def step_check_requirement_fields(context):
    for req in context.current_requirements:
        assert req.req_id, f"Requirement missing ID: {req}"
        assert req.title, f"Requirement missing title: {req}"


@then('at least {count:d} test case should be generated')
def step_check_tc_count(context, count):
    assert len(context.generated_test_cases) >= count, (
        f"Expected at least {count} test case(s), got {len(context.generated_test_cases)}"
    )


@then('each test case should have a title and steps')
def step_check_tc_fields(context):
    for tc in context.generated_test_cases:
        assert tc.title, f"TestCase missing title: {tc.tc_id}"
        assert len(tc.steps) > 0, f"TestCase has no steps: {tc.tc_id}"


@then('at least one test case should be a "{test_type}" type')
def step_check_tc_type_exists(context, test_type):
    types = [tc.test_type for tc in context.generated_test_cases]
    assert test_type in types, (
        f"No test case of type '{test_type}' found. Types present: {set(types)}"
    )


@then('test cases should include "{test_type}" type')
def step_check_includes_type(context, test_type):
    types = [tc.test_type for tc in context.generated_test_cases]
    assert test_type in types, (
        f"Expected test type '{test_type}'. Found: {set(types)}"
    )


@then('I should get at least {count:d} similar requirement')
def step_check_search_results(context, count):
    assert len(context.search_results) >= count, (
        f"Expected at least {count} similar result(s), got {len(context.search_results)}"
    )


@then('the similar requirements should include login-related ones')
def step_check_login_related(context):
    found = any(
        "login" in r["metadata"].get("title", "").lower()
        or "login" in r["document"].lower()
        for r in context.search_results
    )
    assert found, "No login-related requirements in search results"


@then('a CSV file should be created in the output directory')
def step_check_csv_exists(context):
    assert hasattr(context, "csv_output_path"), "CSV output path not set"
    assert os.path.exists(context.csv_output_path), (
        f"CSV file not found: {context.csv_output_path}"
    )


@then('the CSV file should have the correct headers')
def step_check_csv_headers(context):
    from exporters.exporters import CSVExporter
    with open(context.csv_output_path, "r") as f:
        reader = csv.reader(f)
        headers = next(reader)
    for expected in ["TC ID", "Title", "Steps", "Priority"]:
        assert expected in headers, f"Missing header: {expected}. Got: {headers}"


@then('the CSV file should contain {count:d} rows of test data')
def step_check_csv_rows(context, count):
    with open(context.csv_output_path, "r") as f:
        rows = list(csv.reader(f))
    data_rows = len(rows) - 1  # exclude header
    assert data_rows == count, f"Expected {count} rows, got {data_rows}"


@then('a Zephyr CSV file should be created')
def step_check_zephyr_exists(context):
    assert os.path.exists(context.zephyr_output_path), (
        f"Zephyr CSV not found: {context.zephyr_output_path}"
    )


@then('the Zephyr CSV should have "{column}" column')
def step_check_zephyr_column(context, column):
    with open(context.zephyr_output_path, "r") as f:
        reader = csv.reader(f)
        headers = next(reader)
    assert column in headers, f"Missing Zephyr column: '{column}'. Got: {headers}"


@then('the Zephyr CSV should have "Folder" column with value "{expected_folder}"')
def step_check_zephyr_folder(context, expected_folder):
    with open(context.zephyr_output_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert rows, "Zephyr CSV has no data rows"
    folder_value = rows[0].get("Folder", "")
    assert folder_value == expected_folder, (
        f"Expected folder '{expected_folder}', got '{folder_value}'"
    )


@then('test cases should be generated for all requirements')
def step_all_reqs_have_tc(context):
    req_ids = {r.req_id for r in context.current_requirements}
    tc_req_ids = {tc.req_id for tc in context.generated_test_cases}
    missing = req_ids - tc_req_ids
    assert not missing, f"No test cases generated for: {missing}"


@then('both CSV and Zephyr Scale files should be created')
def step_check_both_exports(context):
    from config import config
    csv_path = os.path.join(config.output.output_dir, config.output.csv_filename)
    zephyr_path = os.path.join(config.output.output_dir, config.output.zephyr_filename)
    assert os.path.exists(csv_path), f"CSV not found: {csv_path}"
    assert os.path.exists(zephyr_path), f"Zephyr CSV not found: {zephyr_path}"


@then('a JSON report should be generated')
def step_check_json_report(context):
    assert os.path.exists(context.report_path), f"Report not found: {context.report_path}"


@then('the report should show correct statistics')
def step_check_report_stats(context):
    with open(context.report_path, "r") as f:
        report = json.load(f)
    assert "summary" in report
    assert report["summary"]["total_requirements"] == len(context.current_requirements)
    assert report["summary"]["total_test_cases"] == len(context.generated_test_cases)


# ────────────────────────── HELPERS ───────────────────────────────────────────

def _create_mock_llm():
    """Create a mock LLM client that returns valid structured responses"""
    mock = MagicMock()
    mock.check_connection.return_value = True
    mock.generate_structured.return_value = {
        "test_cases": [
            {
                "title": "Verify successful user login with valid credentials",
                "description": "Verify that a user can log in with correct username and password",
                "preconditions": "User account exists and is active",
                "test_type": "positive",
                "priority": "High",
                "steps": [
                    {"action": "Navigate to login page", "expected_result": "Login page is displayed"},
                    {"action": "Enter valid username", "expected_result": "Username field accepts input"},
                    {"action": "Enter valid password", "expected_result": "Password is masked"},
                    {"action": "Click Login button", "expected_result": "User is logged in successfully"},
                ],
                "expected_outcome": "User is authenticated and redirected to dashboard",
                "given": "user has valid credentials",
                "when": "user submits login form",
                "then": "user is redirected to dashboard",
                "tags": ["login", "authentication"],
                "component": "Authentication",
                "estimated_duration": "5",
            },
            {
                "title": "Verify login fails with invalid credentials",
                "description": "Verify that login is rejected with wrong password",
                "preconditions": "User account exists",
                "test_type": "negative",
                "priority": "High",
                "steps": [
                    {"action": "Navigate to login page", "expected_result": "Login page is displayed"},
                    {"action": "Enter valid username and wrong password", "expected_result": "Credentials entered"},
                    {"action": "Click Login button", "expected_result": "Error message is shown"},
                ],
                "expected_outcome": "Login is rejected with an error message",
                "given": "user has invalid credentials",
                "when": "user submits login form",
                "then": "error message is displayed",
                "tags": ["login", "negative", "security"],
                "component": "Authentication",
                "estimated_duration": "3",
            },
            {
                "title": "Verify login with empty credentials",
                "description": "Verify that form validation works when fields are empty",
                "preconditions": "Login page is accessible",
                "test_type": "edge_case",
                "priority": "Medium",
                "steps": [
                    {"action": "Navigate to login page", "expected_result": "Login page is displayed"},
                    {"action": "Leave username and password empty", "expected_result": "Fields are empty"},
                    {"action": "Click Login button", "expected_result": "Validation error is shown"},
                ],
                "expected_outcome": "Validation errors prevent empty form submission",
                "given": "login page is open",
                "when": "user clicks login without filling fields",
                "then": "validation errors are shown",
                "tags": ["edge_case", "validation"],
                "component": "Authentication",
                "estimated_duration": "3",
            },
        ]
    }
    return mock


def _create_sample_file(full_path: str, file_type: str):
    """Create sample test data files"""
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    if file_type == "txt":
        with open(full_path, "w") as f:
            f.write("""REQ-001 User Login Authentication
Users must be able to log in with a valid username and password combination.
Acceptance Criteria: Valid credentials redirect to dashboard; Invalid credentials show error.

REQ-002 Password Reset Flow
Users can reset forgotten passwords via email verification link.
Acceptance Criteria: Reset email is sent within 60 seconds; Link expires after 24 hours.
""")

    elif file_type == "csv":
        import csv
        with open(full_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "title", "description", "priority", "category"])
            writer.writerow(["REQ-001", "User Login", "Users log in with email/password", "High", "Security"])
            writer.writerow(["REQ-002", "Password Reset", "Users reset password via email", "Medium", "Security"])

    elif file_type == "json":
        import json
        with open(full_path, "w") as f:
            json.dump({
                "requirements": [
                    {"id": "REQ-001", "title": "User Login Authentication",
                     "description": "Users must be able to log in", "priority": "High"},
                    {"id": "REQ-002", "title": "Password Reset",
                     "description": "Users can reset their passwords", "priority": "Medium"},
                ]
            }, f, indent=2)
