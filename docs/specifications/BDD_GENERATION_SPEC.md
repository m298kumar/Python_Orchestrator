# BDD Generation Specification

**Specification ID:** STLC-BDD-001
**Version:** 1.0.0
**Status:** Approved
**Owner:** QA Automation Architecture
**Input contract:** Accepted `TestCaseArtifact` records
**Output contracts:** `FeatureFileArtifact`, `StepDefinitionArtifact`, and POM stubs

## 1. Purpose

This document is the source of truth for converting accepted test cases into readable, traceable, and automatable Gherkin scenarios and supporting code.

The keywords **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are normative.

## 2. Entry criteria

BDD generation MUST consume only test cases that:

- passed the configured test-case quality gate;
- have no unresolved critical semantic issue;
- identify a requirement and target AC;
- have executable actions and observable expected results.

BDD generation MUST NOT conceal or repair a semantically invalid test by rewriting it into valid-looking Gherkin.

## 3. Feature organization

### BDD-GEN-001 — Feature boundary

A feature SHOULD group scenarios by stable business capability or requirement component. It MUST NOT group unrelated behavior merely because tests were generated in the same run.

### BDD-GEN-002 — Traceability tags

Every feature MUST include requirement tags. Every scenario MUST include test type, priority, and stable test-case traceability where supported.

Recommended tags:

```gherkin
@req-001 @tc-0001 @positive @high_priority @user_registration
```

### BDD-GEN-003 — Feature description

The description MUST state business value or behavior, not generator metadata.

## 4. Scenario rules

### BDD-GEN-004 — Scenario title

The title MUST describe behavior and distinguishing condition. It MUST NOT contain truncated AC fragments or generic prefixes without meaningful content.

### BDD-GEN-005 — Given

Given establishes state only. It MUST NOT perform the primary action or contradict the authentication context.

### BDD-GEN-006 — When

When contains the single primary business action or event. Supporting actions MAY use `And` when essential.

### BDD-GEN-007 — Then

Then states externally observable evidence. It MUST NOT merely repeat “the system responds as described” or paraphrase the AC without a concrete assertion.

### BDD-GEN-008 — Step consistency

Gherkin must remain semantically consistent with the detailed test steps. Important validations MUST NOT be discarded when the test is condensed.

### BDD-GEN-009 — Declarative language

Feature files SHOULD describe business behavior. Low-level click and selector mechanics belong in step definitions or page objects unless the UI control itself is the behavior under specification.

### BDD-GEN-010 — Scenario independence

Scenarios MUST be independently executable and MUST NOT depend on execution order or state left by another scenario.

### BDD-GEN-011 — Background

Background MAY contain only state shared by every scenario in the feature. Authentication MUST NOT be placed in Background when any scenario covers public behavior.

### BDD-GEN-012 — Scenario Outlines

A Scenario Outline SHOULD be used when scenarios have the same behavior and differ only by data. Every placeholder MUST have a matching Examples column, and each row MUST represent a meaningful equivalence class or boundary.

## 5. Automation binding rules

### BDD-AUTO-001 — Step definitions

Every generated Given, When, Then, and And step MUST have exactly one matching step-definition pattern after normalization.

### BDD-AUTO-002 — No hollow implementations

Generated step definitions MUST NOT silently pass, contain only `TODO`, or use assertions that always succeed. Skeletons MUST be clearly marked non-executable until implemented.

### BDD-AUTO-003 — Selector provenance

Selectors injected from crawler data MUST include source application origin and page URL. A selector from a different origin MUST NOT be used.

### BDD-AUTO-004 — Locator priority

Prefer stable accessible or unique locators in this order:

1. test-specific stable identifier
2. accessible role and name
3. unique ID
4. stable label association
5. stable CSS selector
6. XPath fallback

### BDD-AUTO-005 — Data isolation

Generated automation MUST create or identify unique test data where collisions are possible, especially email addresses and account identifiers.

### BDD-AUTO-006 — Assertions

Assertions MUST verify the evidence required by the scenario Then steps. Navigation alone is not proof of persistence, authentication, or authorization.

## 6. Gherkin validation gate

A feature is accepted only when:

- it contains one Feature and at least one Scenario or Scenario Outline;
- scenario names are unique within the feature;
- each scenario contains Given, When, and Then semantics;
- Scenario Outline placeholders and Examples columns match;
- tags are syntactically valid;
- no step is empty, truncated, or generic;
- requirement and test-case traceability is present;
- scenario polarity agrees with the source test and AC;
- selector origins match the application under test;
- all generated steps resolve to step definitions.

## 7. Compliant example

```gherkin
@req-001 @user_registration
Feature: New visitor account registration
  First-time visitors can create an account without prior authentication.

  @tc-0004 @negative @high_priority
  Scenario: Reject a registration password shorter than four characters
    Given the visitor is signed out and the public Registration page is open
    And valid unique registration details have been entered
    When the visitor enters "abc" in the Password field and selects Continue
    Then the Registration page remains displayed
    And an inline password-length validation error is shown
```

Non-compliant behavior includes requiring a login for this scenario, using “Then the system responds correctly,” or binding the step to a selector crawled from another application.

## 8. Audit output

BDD generation SHOULD record:

- source requirement and test-case IDs;
- specification version;
- feature and scenario counts;
- outline grouping decisions;
- validation warnings and failures;
- generated step-definition coverage;
- selector source URL and origin;
- unresolved skeleton steps.

## 9. Change control

Generated features SHOULD record this specification version in artifact metadata. Changes affecting Gherkin acceptance or automation binding require a version increment.
