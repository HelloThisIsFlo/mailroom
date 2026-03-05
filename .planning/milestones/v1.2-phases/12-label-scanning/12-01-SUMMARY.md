---
phase: 12-label-scanning
plan: 01
subsystem: workflow
tags: [jmap, batching, email-query, error-handling, structlog]

# Dependency graph
requires:
  - phase: 11-config-layer
    provides: triage_labels property and resolved_categories for label enumeration
provides:
  - Batched _collect_triaged() with single JMAP round-trip for email discovery
  - Per-method error detection with escalating log severity and self-healing counters
  - Pagination follow-up for labels with total > limit
affects: [13-re-triage]

# Tech tracking
tech-stack:
  added: []
  patterns: [batched-jmap-query, per-method-error-detection, escalating-failure-counter]

key-files:
  created: []
  modified:
    - src/mailroom/workflows/screener.py
    - tests/test_screener_workflow.py

key-decisions:
  - "Error filtering (@MailroomError check) stays as separate jmap.call() after batch -- cannot batch without result references"
  - "Escalation threshold set to 3 consecutive failures (3 polls = ~3 minutes before ERROR level)"
  - "Pagination handled via follow-up query_emails() for any label with total > len(ids)"
  - "structlog.testing.capture_logs() used for log-level assertions in tests (not caplog)"

patterns-established:
  - "_make_batched_call_side_effect: reusable test helper for mocking batched Email/query + Email/get + Email/set"
  - "_default_call_side_effect: jmap fixture default handles all three JMAP method types"

requirements-completed: [SCAN-01, SCAN-02, SCAN-03]

# Metrics
duration: 8min
completed: 2026-03-03
---

# Phase 12 Plan 01: Batched Label Scanning Summary

**Batched Email/query discovery replacing N sequential calls with 1 JMAP round-trip, plus per-method error detection with escalating WARNING/ERROR severity**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-03T19:45:54Z
- **Completed:** 2026-03-03T19:53:44Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- Replaced sequential per-label `query_emails()` loop with single batched `jmap.call()` containing N Email/query method calls
- Added `_label_failure_counts` dict and `_handle_label_query_failure()` helper for per-method error detection
- Escalating log severity: WARNING for first 2 failures, ERROR at 3+ consecutive failures, auto-reset on success
- Pagination follow-up: when any label's `total > len(ids)`, falls back to `query_emails()` for that label
- Single `get_email_senders()` call for ALL emails across ALL successful labels
- Updated 13 existing test fixtures to use batched mock pattern; added 17 new tests

## Task Commits

Each task was committed atomically:

1. **RED: Failing tests for batched discovery** - `4ceeb38` (test)
2. **GREEN: Batched _collect_triaged() implementation** - `5d8728f` (feat)

## Files Created/Modified
- `src/mailroom/workflows/screener.py` - Refactored `_collect_triaged()` for batched queries, added `_label_failure_counts` and `_handle_label_query_failure()`
- `tests/test_screener_workflow.py` - Added `TestBatchedCollectTriaged` (10 tests), `TestBatchedPerMethodError` (5 tests), `TestBatchedPagination` (1 test), `TestBatchedExistingBehaviorPreserved` (1 test); updated 13 existing test fixtures

## Decisions Made
- Error filtering (@MailroomError check) stays as a separate `jmap.call()` after batch discovery -- it needs email IDs from query results and result references are rejected per CONTEXT.md
- Escalation threshold: 3 consecutive failures before ERROR level -- 3 polls at ~60s interval means ~3 minutes of degradation before escalating
- Pagination handled via follow-up `query_emails()` for any label with `total > len(ids)`, with a log.warning about pagination needed
- Used `structlog.testing.capture_logs()` for testing log levels instead of pytest's `caplog` (structlog uses PrintLogger, not standard logging)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Batched discovery infrastructure ready for Phase 13 (re-triage)
- `_collect_triaged()` return signature unchanged -- Phase 13 can extend it as needed
- `_label_failure_counts` available as instance variable for monitoring/debugging

---
*Phase: 12-label-scanning*
*Completed: 2026-03-03*
