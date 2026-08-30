# Test Case Generation Specification

**Specification ID:** STLC-TC-001
**Version:** 1.0.0
**Status:** Approved
**Owner:** QA Architecture
**Input contract:** `RequirementArtifact`
**Output contract:** `TestCaseArtifact`

## 1. Purpose

This document is the source of truth for generating complete, executable, semantically correct test cases from captured requirements.

The keywords **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are normative.

## 2. Traceability model

Every test case MUST trace to:

- exactly one primary `req_id`;
- exactly one target acceptance criterion;
- the specification version used;
- any retrieved RAG example IDs;
- any crawler or feedback context used.

One acceptance criterion MAY produce multiple tests, but a test MUST NOT claim coverage of an AC it does not assert.

## 3. Required test-case fields

| Field | Rule |
|---|---|
| `tc_id` | Unique within the run |
| `req_id` | Exact source requirement ID |
| `title` | Specific behavior and condition; no generic “verify functionality” wording |
| `description` | Purpose and scope of this test only |
| `preconditions` | Only state that must exist before execution |
| `test_type` | `positive`, `negative`, `edge_case`, `security`, or approved extension |
| `priority` | Derived from risk and source priority |
| `steps` | Ordered, executable actions with observable results |
| `expected_outcome` | Final evidence that proves the target AC |
| `component` | Specific screen, API, service, or module |
| `given`, `when`, `then` | Concise semantic summary consistent with detailed steps |
| `test_level` | `unit`, `api`, `integration`, or `e2e`, justified by observability |
| `quality_score` | Score produced by the configured gate |
| `quality_issues` | All known structural and semantic defects |

## 4. Generation rules

### TC-GEN-001 — AC fidelity

Actions and expected results MUST preserve the target AC’s actor, condition, polarity, values, and observable outcome.

### TC-GEN-002 — No contradiction

A test MUST NOT require authentication for explicitly public behavior, expect acceptance of explicitly invalid data, reverse allow/deny semantics, or replace a success-path assertion with an unrelated rejection assertion.

### TC-GEN-003 — One purpose

Each test SHOULD validate one primary behavior. Additional assertions are allowed only when they are necessary evidence for the same behavior.

### TC-GEN-004 — Concrete actions

Every action MUST identify the page or endpoint, element or parameter, operation, and concrete test data when known.

### TC-GEN-005 — Observable expected results

Every expected result MUST identify visible UI state, exact or pattern-based message, response status/body, persisted record state, event, or measurable value. “Works correctly” and equivalent phrases are prohibited.

### TC-GEN-006 — No invented exact text

Exact error messages MUST be asserted only when supplied by a trusted source or verified crawler/API context. Otherwise, assert the required meaning or error category and mark the exact text as unspecified.

### TC-GEN-007 — Correct test type

- Positive tests prove permitted or successful behavior.
- Negative tests prove explicit rejection, protection, or failure handling.
- Edge tests require a real boundary, threshold, transition, concurrency condition, or rare state.
- Security tests require a stated or risk-derived security property and appropriate evidence.

The generator MUST NOT assign test types merely by cycling through labels.

### TC-GEN-008 — Boundary construction

For a numeric threshold `N`, boundary coverage SHOULD include `N-1`, `N`, and `N+1` when meaningful. For formats, valid and invalid equivalence classes MUST be logically correct.

### TC-GEN-009 — Preconditions

Preconditions MUST NOT perform the behavior under test. Public registration, for example, MUST NOT require an already authenticated user unless the requirement says so.

### TC-GEN-010 — Persistence claims

Claims such as “no record created,” “value persisted,” or “audit event written” MUST include a database, API, event, or behaviorally equivalent verification step.

### TC-GEN-011 — Test level

`test_level` MUST reflect the layer being observed. UI navigation is not a unit test. Cross-service persistence is not proven by UI text alone.

### TC-GEN-012 — RAG is advisory

Retrieved examples MAY guide style and coverage but MUST NOT override the current requirement. Retrieved content from another project, domain, or application MUST be filtered or clearly scoped.

## 5. Mandatory semantic validation

Before acceptance, the validator MUST compare the target AC with:

- preconditions;
- test type;
- every action and expected result;
- final expected outcome;
- Given/When/Then summary.

It MUST detect at least:

- authentication-context contradiction;
- positive/negative polarity reversal;
- malformed data expected to succeed;
- boundary language without a boundary;
- expected outcome unrelated to the target AC;
- persistence claims without persistence evidence;
- duplicate tests with materially identical behavior;
- unsupported exact messages or values;
- truncated or malformed output.

Semantic defects MUST force regeneration or human review regardless of the structural score.

## 6. Quality gate

A test is accepted only when:

- `quality_score >= accept_threshold`;
- no critical semantic issue exists;
- required fields are complete;
- steps are executable and non-repetitive;
- the expected outcome proves the target AC.

A test is eligible for RAG promotion only when:

- it is accepted;
- `quality_score >= auto_example_threshold`;
- `quality_issues` is empty;
- it was not produced by fallback synthesis after generation failure;
- it has explicit human approval. Automatic promotion is prohibited.

## 7. Compliant example

Target AC:

> Passwords shorter than 4 characters are rejected with an inline error.

```text
Title: Reject a three-character registration password
Preconditions: Visitor is signed out and the public Registration page is open.
Step 1: Enter valid unique registration data and enter "abc" in Password.
Expected: Password field contains three masked characters.
Step 2: Select Continue.
Expected: Registration remains on the same page and an inline password validation error is shown.
Expected outcome: No account is created and the password-length rule is reported.
```

Non-compliant examples include logging in first, expecting `abc` to succeed, or asserting database non-creation without evidence.

## 8. Audit output

Each generated test SHOULD record:

- target AC identifier or index;
- classified AC and test type with reason;
- generation and regeneration attempts;
- quality dimension scores;
- semantic validation findings;
- RAG documents retrieved and similarity scores;
- whether the case was promoted to RAG and why.

## 9. Change control

Generated test cases SHOULD record this specification version. A rule change that alters acceptance behavior requires a minor or major version increment.
