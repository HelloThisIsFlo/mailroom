---
phase: 06-configurable-categories
plan: 01
subsystem: config
tags: [pydantic, validation, dataclass, tdd, triage-categories]

# Dependency graph
requires:
  - phase: 05-documentation-deployment-showcase
    provides: v1.0 complete config with 9 hardcoded label/group fields
provides:
  - TriageCategory Pydantic input model with name validation
  - ResolvedCategory frozen dataclass with all concrete fields
  - Derivation functions (label, contact_group, destination_mailbox from name)
  - _default_categories() factory returning 5 v1.0 defaults
  - resolve_categories() with two-pass resolution and full validation
  - _validate_categories() collecting all errors at once
affects: [06-02, 07-setup-script]

# Tech tracking
tech-stack:
  added: []
  patterns: [TriageCategory input model, ResolvedCategory frozen output, two-pass parent resolution, all-at-once validation]

key-files:
  created: []
  modified:
    - src/mailroom/core/config.py
    - tests/test_config.py

key-decisions:
  - "Validation is a standalone function (_validate_categories) separate from resolve_categories, enabling Plan 02 to wire it into MailroomSettings model_validator"
  - "Two-pass resolution: first pass derives own fields, second pass inherits from parents -- handles any declaration order"
  - "Error formatting includes default config JSON (model_dump with exclude_none) for copy-paste reference"

patterns-established:
  - "TriageCategory as user input model (name-only minimum, everything else optional/derived)"
  - "ResolvedCategory as frozen output consumed by service logic (all fields concrete)"
  - "Derivation rules: label=@To{NameNoSpaces}, group=Name, mailbox=Name"
  - "Validation collects all errors into list[str] before raising single ValueError"

requirements-completed: [CONFIG-01, CONFIG-02, CONFIG-03, CONFIG-06]

# Metrics
duration: 4min
completed: 2026-02-26
---

# Phase 6 Plan 01: Category Models and Validation Summary

**TriageCategory input model, ResolvedCategory frozen output, name-based derivation rules, 5-category default factory, and all-at-once validation covering 6+ error types**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-26T00:20:28Z
- **Completed:** 2026-02-26T00:24:03Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- TriageCategory Pydantic model with name validation (strip whitespace, reject empty), optional overrides, and Literal contact_type
- ResolvedCategory frozen dataclass with all concrete fields (no Optional except parent)
- Derivation rules producing correct label/group/mailbox from category name
- Default factory returning 5 categories matching exact v1.0 behavior (Imbox->Inbox, Person inherits from Imbox)
- Comprehensive validation: empty list, duplicate names, non-existent parents, circular chains, duplicate labels, shared groups without parent relationship
- All errors collected and reported at once with default config JSON for reference
- 28 new tests alongside 18 existing tests -- zero regressions (46 total in test_config.py, 208 in full suite)

## Task Commits

Each task was committed atomically:

1. **Task 1: TDD the TriageCategory model, ResolvedCategory, derivation rules, and defaults**
   - `580dc16` (test) RED: failing tests for model, derivation, defaults, parent inheritance
   - `e45f232` (feat) GREEN: implement TriageCategory, ResolvedCategory, derivation, defaults, resolve_categories

2. **Task 2: TDD the validation logic**
   - `49ca79f` (test) RED: failing tests for all validation scenarios
   - `b8347ac` (feat) GREEN: implement _validate_categories with all-at-once error collection

_TDD tasks: 2 RED commits + 2 GREEN commits. No REFACTOR commits needed -- code was clean from GREEN phase._

## Files Created/Modified
- `src/mailroom/core/config.py` - Added TriageCategory model, ResolvedCategory dataclass, derivation functions, _default_categories factory, _validate_categories, resolve_categories (all ADDITIVE -- existing MailroomSettings untouched)
- `tests/test_config.py` - Added 28 new tests in 11 test classes covering model, derivation, defaults, frozen dataclass, parent inheritance, and 6+ validation scenarios

## Decisions Made
- Validation is a standalone `_validate_categories()` function separate from `resolve_categories()` -- Plan 02 can wire it into `MailroomSettings.model_validator` cleanly
- Two-pass resolution handles parent-before-child and child-before-parent ordering without sorting user input
- Default config JSON in error messages uses `model_dump(exclude_none=True)` for clean, copy-pasteable output

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All models and validation ready for Plan 02 to wire into MailroomSettings
- Plan 02 will add `triage_categories: list[TriageCategory]` field with `default_factory=_default_categories`
- Plan 02 will replace 9 hardcoded fields with resolved category properties
- No blockers

## Self-Check: PASSED

All files exist. All 4 commits verified (580dc16, e45f232, 49ca79f, b8347ac). 46/46 tests pass in test_config.py, 208/208 in full suite.

---
*Phase: 06-configurable-categories*
*Completed: 2026-02-26*
