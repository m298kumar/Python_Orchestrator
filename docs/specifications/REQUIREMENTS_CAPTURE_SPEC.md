# Requirements Capture Specification

**Specification ID:** STLC-REQ-001
**Version:** 1.0.0
**Status:** Approved
**Owner:** Product and QA Architecture
**Applies to:** Every source document accepted by the requirements ingestion workflow

## 1. Purpose

This document is the source of truth for converting business specifications into `RequirementArtifact` records. Its purpose is to preserve meaning, traceability, and testability before any test generation begins.

The keywords **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are normative.

## 2. Source precedence

When sources disagree, the system MUST use this precedence and record the conflict:

1. Explicit acceptance criteria attached to the requirement
2. Requirement description
3. Requirement title
4. Structured source fields such as priority and category
5. Inferred values

The system MUST NOT silently resolve conflicting normative statements.

## 3. Required output contract

Every captured requirement MUST contain:

| Field | Rule |
|---|---|
| `req_id` | Required, stable within the project, preserved from the source when supplied |
| `title` | Required, concise statement of the capability or constraint |
| `description` | Required, complete behavior and business context without invented details |
| `priority` | Required; use source value or `Medium` when absent and mark it as defaulted |
| `category` | Required; use source value or `Functional` when absent and mark it as defaulted |
| `acceptance_criteria` | Required, one independently testable behavior per item |
| `tags` | Optional normalized labels; inferred tags MUST be distinguishable from source tags |
| `raw_text` | Original source excerpt sufficient for audit and traceability |

## 4. Capture rules

### REQ-CAP-001 — Preserve source meaning

The captured requirement MUST preserve actors, conditions, actions, constraints, expected outcomes, URLs, numeric limits, error messages, and security rules stated by the source.

### REQ-CAP-002 — No invention

The capture stage MUST NOT invent field limits, UI labels, error text, credentials, database behavior, redirects, or business rules.

### REQ-CAP-003 — Atomic acceptance criteria

Each acceptance criterion SHOULD express one observable rule. Compound source criteria MUST be split only when each resulting criterion remains faithful to the original text.

### REQ-CAP-004 — Testability

An acceptance criterion MUST identify, explicitly or by faithful normalization:

- the starting condition or trigger;
- the action or event;
- the observable result.

Criteria such as “works correctly,” “is user friendly,” or “performs well” MUST be flagged as ambiguous unless a measurable definition exists.

### REQ-CAP-005 — Exact values

URLs, status codes, field names, quoted messages, durations, quantities, formats, roles, and thresholds MUST be retained exactly.

### REQ-CAP-006 — Polarity

The capture stage MUST preserve whether behavior is permitted, required, rejected, blocked, optional, or prohibited. It MUST NOT reverse positive and negative meaning.

### REQ-CAP-007 — Authentication context

Public, anonymous, authenticated, and role-restricted behavior MUST remain explicit. “Without authentication” MUST NOT be normalized into an authenticated precondition.

### REQ-CAP-008 — Source location

Each requirement SHOULD retain source metadata containing filename and, where available, sheet/row, page, section, or JSON path.

### REQ-CAP-009 — Duplicate handling

Requirements with the same project and `req_id` MUST be compared by content. Identical content is the same version; changed content is a new revision and MUST NOT be silently discarded.

### REQ-CAP-010 — Application target

Application URLs found in the requirement MUST be captured as target context. If multiple origins are present, the system MUST require an explicit crawler target rather than choosing one arbitrarily.

## 5. Validation gate

A requirement is generation-ready only when:

- `req_id`, title, and description are non-empty;
- at least one acceptance criterion exists;
- every criterion is non-empty and independently traceable;
- no unresolved critical conflict exists;
- numeric and quoted values match the source;
- URLs are syntactically valid;
- ambiguity warnings are recorded.

Invalid requirements MUST be returned for review and MUST NOT silently enter test generation.

## 6. Example

Source:

> Registration is public. Passwords shorter than four characters are rejected with an inline error.

Compliant capture:

```json
{
  "req_id": "REQ-001",
  "title": "New Visitor Account Registration",
  "description": "First-time visitors can create an account without prior authentication.",
  "priority": "High",
  "category": "User Registration",
  "acceptance_criteria": [
    "The registration form is publicly accessible without prior authentication.",
    "Passwords shorter than 4 characters are rejected with an inline error."
  ]
}
```

Non-compliant capture:

- Adds an administrator approval rule not present in the source.
- Replaces “without prior authentication” with “user is logged in.”
- Changes four characters to six characters.

## 7. Audit output

The capture stage SHOULD emit:

- source filename and location;
- parsed requirement count;
- rejected requirement count and reasons;
- ambiguity and conflict warnings;
- content hash and revision identifier;
- inferred fields and their inference reason.

## 8. Change control

Changes to this specification require a version increment. Generated artifacts SHOULD record the specification version used for capture.
