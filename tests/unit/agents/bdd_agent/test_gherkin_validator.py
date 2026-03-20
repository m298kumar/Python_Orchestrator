"""Tests for GherkinValidator."""

import pytest
from stlc_platform.agents.bdd_agent.gherkin_validator import GherkinValidator


@pytest.fixture
def validator():
    return GherkinValidator()


VALID_FEATURE = """\
@REQ-001
Feature: Product Search
  Users can search for products.

  Scenario: Search by keyword
    Given A user on the search page
    When The user enters a keyword
    Then Search results are displayed
"""

VALID_WITH_BACKGROUND = """\
Feature: Shopping Cart

  Background:
    Given A logged-in user

  Scenario: Add to cart
    When The user clicks Add to Cart
    Then The product is in the cart

  Scenario: Remove from cart
    When The user clicks Remove
    Then The cart is empty
"""

VALID_OUTLINE = """\
Feature: Login

  Scenario Outline: Login with credentials
    Given A user on the login page
    When The user enters <username> and <password>
    Then The system responds with <result>

    Examples:
      | username | password | result  |
      | admin    | pass123  | success |
      | guest    | wrong    | failure |
"""


class TestValidGherkin:
    def test_valid_simple_feature(self, validator):
        result = validator.validate(VALID_FEATURE)
        assert result.valid is True
        assert result.errors == []
        assert result.feature_title == "Product Search"
        assert result.scenario_count == 1

    def test_valid_with_background(self, validator):
        result = validator.validate(VALID_WITH_BACKGROUND)
        assert result.valid is True
        assert result.scenario_count == 2

    def test_valid_scenario_outline(self, validator):
        result = validator.validate(VALID_OUTLINE)
        assert result.valid is True
        assert result.scenario_count == 1

    def test_valid_with_and_steps(self, validator):
        content = """\
Feature: Multi-step

  Scenario: Multiple steps
    Given A user is logged in
    And The user has items in cart
    When The user clicks checkout
    And Confirms the order
    Then An order is created
    And A confirmation email is sent
"""
        result = validator.validate(content)
        assert result.valid is True


class TestInvalidGherkin:
    def test_missing_feature_keyword(self, validator):
        content = """\
Scenario: Orphan scenario
    Given Something
    When Something else
    Then Result
"""
        result = validator.validate(content)
        assert result.valid is False
        assert any("Missing 'Feature:'" in e for e in result.errors)

    def test_no_scenarios(self, validator):
        content = "Feature: Empty feature\n  No scenarios here.\n"
        result = validator.validate(content)
        assert result.valid is False
        assert any("No Scenario" in e for e in result.errors)

    def test_scenario_missing_when(self, validator):
        content = """\
Feature: Bad
  Scenario: No when
    Given Something
    Then Result
"""
        result = validator.validate(content)
        assert result.valid is False
        assert any("missing a 'When' step" in e for e in result.errors)

    def test_scenario_missing_then(self, validator):
        content = """\
Feature: Bad
  Scenario: No then
    Given Something
    When Action
"""
        result = validator.validate(content)
        assert result.valid is False
        assert any("missing a 'Then' step" in e for e in result.errors)

    def test_outline_without_examples(self, validator):
        content = """\
Feature: Bad
  Scenario Outline: No examples
    Given A <thing>
    When Action on <thing>
    Then Result for <thing>
"""
        result = validator.validate(content)
        assert result.valid is False
        assert any("missing an 'Examples:'" in e for e in result.errors)


class TestDuplicateScenarios:
    def test_duplicate_names_produce_warning(self, validator):
        content = """\
Feature: Dupes
  Scenario: Same name
    Given A
    When B
    Then C

  Scenario: Same name
    Given X
    When Y
    Then Z
"""
        result = validator.validate(content)
        # Duplicates are warnings, not errors
        assert result.valid is True
        assert any("Duplicate scenario name" in w for w in result.warnings)


class TestTagValidation:
    def test_well_formed_tags_pass(self, validator):
        result = validator.validate(VALID_FEATURE)
        assert not any("Malformed tag" in e for e in result.errors)

    def test_malformed_tag_detected(self, validator):
        content = """\
@valid_tag @bad.tag!here
Feature: Tag test
  Scenario: S1
    Given A
    When B
    Then C
"""
        result = validator.validate(content)
        assert any("Malformed tag" in e for e in result.errors)
