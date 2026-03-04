---
phase: 13-re-triage
plan: 03
subsystem: testing
tags: [human-tests, re-triage, integration-testing, fastmail, end-to-end]

# Dependency graph
requires:
  - phase: 13-re-triage
    plan: 02
    provides: "Re-triage detection and execution in _process_sender with group reassignment and email reconciliation"
provides:
  - "test_17_retriage.py: end-to-end re-triage human integration test against live Fastmail"
  - "test_9_already_grouped.py deprecated with early exit redirecting to test_17"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Human test deprecation: early exit with redirect message before imports"

key-files:
  created:
    - human-tests/test_17_retriage.py
  modified:
    - human-tests/test_9_already_grouped.py
    - src/mailroom/clients/jmap.py
    - src/mailroom/workflows/screener.py

key-decisions:
  - "JMAP pagination uses len-based check instead of total field (total requires calculateTotal: true)"
  - "_apply_warning_label mailbox lookup moved inside try/except for true non-blocking behavior"
  - "Human tests use settings.required_mailboxes instead of hand-rolled mailbox lists"

patterns-established:
  - "Human test deprecation pattern: print redirect, sys.exit(0) before imports"
  - "Human tests should use settings.required_mailboxes for mailbox resolution (DRY)"

requirements-completed: [RTRI-05]

# Metrics
duration: 11min
completed: 2026-03-03
---

# Phase 13 Plan 03: Human Integration Tests Summary

**End-to-end re-triage human test (test_17) validating group reassignment, email label reconciliation, and triage history against live Fastmail, with test_9 deprecated via early exit**

## Performance

- **Duration:** 11 min (including human verification checkpoint)
- **Started:** 2026-03-03T23:40:00Z
- **Completed:** 2026-03-03T23:51:04Z
- **Tasks:** 2 (1 auto + 1 human-verify checkpoint)
- **Files modified:** 3

## Accomplishments
- Created test_17_retriage.py: comprehensive end-to-end re-triage test that validates group move, email label reconciliation (260 emails), triage label removal, Screener label cleanup, and contact note history
- Deprecated test_9_already_grouped.py with early exit redirecting to test_17 (already-grouped error replaced by re-triage in Phase 13)
- Human verification passed all 7 checks against live Fastmail: contact moved from Bank to Feed, 260 emails reconciled with correct labels, old labels removed, triage label removed, contact note updated with "Re-triaged" entry
- Fixed JMAP pagination bug discovered during live testing (total field not returned without calculateTotal)

## Task Commits

Each task was committed atomically:

1. **Task 1: test_9 early exit + test_17 re-triage human test** - `c351369` (feat)
2. **Task 2: Human verification checkpoint** - approved (no commit, verification only)

**Additional fixes (during verification):**
- `d49b4f2` (fix: len-based pagination instead of JMAP total field)
- `5cdd897` (fix: warning label lookup inside try/except, use required_mailboxes in test_17)

## Files Created/Modified
- `human-tests/test_17_retriage.py` - End-to-end re-triage human integration test (401 lines)
- `human-tests/test_9_already_grouped.py` - Early exit with redirect message to test_17
- `src/mailroom/clients/jmap.py` - Fixed pagination in query_emails() and query_emails_by_sender()
- `src/mailroom/workflows/screener.py` - Fixed _apply_warning_label non-blocking behavior

## Decisions Made
- JMAP pagination uses `len(ids) < limit` check instead of `total` field, since JMAP Email/query omits `total` unless `calculateTotal: true` is set -- simpler and more resilient
- `_apply_warning_label` mailbox lookup moved inside try/except to match "non-blocking" docstring contract
- Human tests use `settings.required_mailboxes` instead of hand-rolled mailbox lists (DRY, stays in sync)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] JMAP pagination used missing total field**
- **Found during:** Task 2 (human verification -- live Fastmail testing)
- **Issue:** `query_emails()` and `query_emails_by_sender()` paginated using the `total` field from JMAP Email/query responses, but JMAP servers omit `total` unless `calculateTotal: true` is explicitly set. This caused pagination to stop after the first page for senders with many emails.
- **Fix:** Replaced `total`-based pagination with `len(ids) < limit` check -- if fewer results than requested, we've reached the end. Simpler and does not depend on optional JMAP response fields.
- **Files modified:** `src/mailroom/clients/jmap.py`
- **Verification:** Live Fastmail test successfully paginated and reconciled 260 emails for a single sender
- **Committed in:** `d49b4f2`

**2. [Rule 1 - Bug] _apply_warning_label mailbox lookup outside try/except**
- **Found during:** Task 2 (human verification -- live Fastmail testing with name-mismatched contact)
- **Issue:** `_apply_warning_label` docstring said "non-blocking" but the mailbox ID lookup was outside the try block. When `@MailroomWarning` was missing from `mailbox_ids` (due to test script bug #3), KeyError crashed the entire flow before email reconciliation could run.
- **Fix:** Moved mailbox lookup inside the existing try/except block.
- **Files modified:** `src/mailroom/workflows/screener.py`
- **Committed in:** `5cdd897`

**3. [Rule 1 - Bug] test_17 used hand-rolled mailbox list missing @MailroomWarning**
- **Found during:** Task 2 (human verification -- live Fastmail testing)
- **Issue:** Test script manually listed mailboxes but omitted `@MailroomWarning`. When a name mismatch triggered the warning path, the mailbox ID was missing from the dict.
- **Fix:** Replaced hand-rolled list with `settings.required_mailboxes` (single source of truth).
- **Files modified:** `human-tests/test_17_retriage.py`
- **Committed in:** `5cdd897`

---

**Total deviations:** 3 auto-fixed (3 bugs)
**Impact on plan:** All bugs found and fixed during human verification checkpoint. Human tests are first-class citizens — they caught issues unit tests couldn't.

## Issues Encountered
None remaining — all issues found during checkpoint were fixed inline.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 13 (Re-triage) is COMPLETE -- all 3 plans executed
- v1.2 milestone (Triage Pipeline v2) is COMPLETE -- all 4 phases (10-13) executed
- Remaining: CLOSE-01 (finalize docs/WIP.md into proper documentation)

## Self-Check: PASSED

All files and commits verified:
- human-tests/test_17_retriage.py: FOUND
- human-tests/test_9_already_grouped.py: FOUND
- src/mailroom/clients/jmap.py: FOUND
- Commit c351369: FOUND
- Commit d49b4f2: FOUND
- Commit 5cdd897: FOUND

---
*Phase: 13-re-triage*
*Completed: 2026-03-04*
