@orchestrator
Feature: AI Test Case Generation Orchestrator
  As a QA engineer
  I want to generate test cases from requirements using AI
  So that I can create comprehensive test coverage quickly

  Background:
    Given the Ollama LLM server is running with model "llama3.2"
    And the ChromaDB vector store is initialized

  @smoke @requirements_reading
  Scenario Outline: Read requirements from various file formats
    Given I have a requirements file "<file_type>" at "<file_path>"
    When I read the requirements file
    Then I should get at least 1 requirement
    And each requirement should have an ID and title

    Examples:
      | file_type | file_path                          |
      | txt       | test_data/sample_requirements.txt  |
      | csv       | test_data/sample_requirements.csv  |
      | json      | test_data/sample_requirements.json |

  @smoke @llm_generation
  Scenario: Generate test cases for a single requirement
    Given I have a requirement with ID "REQ-001"
    And the requirement title is "User Login Authentication"
    And the requirement description is "Users must be able to log in with valid username and password"
    When I generate test cases for the requirement
    Then at least 1 test case should be generated
    And each test case should have a title and steps
    And at least one test case should be a "positive" type

  @regression @llm_generation
  Scenario: Generate positive and negative test cases
    Given I have a requirement with ID "REQ-002"
    And the requirement title is "Password Reset"
    And the requirement description is "Users can reset their password via email link"
    And test generation is configured with negative tests enabled
    When I generate test cases for the requirement
    Then test cases should include "positive" type
    And test cases should include "negative" type

  @regression @chroma_db
  Scenario: Store requirements in ChromaDB and retrieve similar
    Given I have the following requirements:
      | req_id  | title                    | description                                 |
      | REQ-010 | Login with email         | User logs in using email and password       |
      | REQ-011 | Login with SSO           | User logs in using Single Sign-On provider  |
      | REQ-012 | Password complexity rule | Password must contain special characters    |
    When I add all requirements to the vector store
    And I search for requirements similar to "user authentication and login"
    Then I should get at least 1 similar requirement
    And the similar requirements should include login-related ones

  @export @csv
  Scenario: Export test cases to standard CSV format
    Given I have 3 generated test cases for "REQ-001"
    When I export the test cases to CSV format
    Then a CSV file should be created in the output directory
    And the CSV file should have the correct headers
    And the CSV file should contain 3 rows of test data

  @export @zephyr
  Scenario: Export test cases to Zephyr Scale format
    Given I have 3 generated test cases for "REQ-001"
    When I export the test cases to Zephyr Scale format
    Then a Zephyr CSV file should be created
    And the Zephyr CSV should have "Name" column
    And the Zephyr CSV should have "Test Script (Step-by-Step)" column
    And the Zephyr CSV should have "Folder" column with value "Generated Tests/REQ-001"

  @end_to_end
  Scenario: Full orchestration pipeline from requirements file to Zephyr export
    Given I have a requirements CSV file with 2 requirements
    When I run the full orchestration pipeline
    Then test cases should be generated for all requirements
    And both CSV and Zephyr Scale files should be created
    And a JSON report should be generated
    And the report should show correct statistics
