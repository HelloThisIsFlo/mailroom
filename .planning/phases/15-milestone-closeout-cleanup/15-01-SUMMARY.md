---
phase: 15-milestone-closeout-cleanup
plan: 01
subsystem: testing, api
tags: [dead-code-removal, structlog, infrastructure-groups, carddav]

# Dependency graph
requires:
  - phase: 13-re-triage
    provides: "_reconcile_email_labels() replaced _get_destination_mailbox_ids and batch_move_emails"
  - phase: 14-contact-provenance
    provides: "infrastructure_groups pattern in __main__.py validate_groups call"
provides:
  - "Clean production code with no dead methods"
  - "Consistent infrastructure_groups handling across triage and reset paths"
  - "Structlog test isolation via configure_logging mock"
  - "RTRI-04 requirement wording aligned with code behavior"
affects: [15-02]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Mock configure_logging in tests that call run_reset() to prevent structlog cross-contamination"

key-files:
  created: []
  modified:
    - src/mailroom/reset/resetter.py
    - tests/test_resetter.py
    - src/mailroom/workflows/screener.py
    - src/mailroom/clients/jmap.py
    - tests/test_screener_workflow.py
    - tests/test_jmap_client.py
    - .planning/REQUIREMENTS.md

key-decisions:
  - "Replaced batch_move_emails.assert_not_called() with jmap.call.assert_not_called() since batch_move_emails no longer exists"
  - "Updated docstring reference to batch_move_emails to remove dead code mention"

patterns-established:
  - "infrastructure_groups kwarg required on all validate_groups calls (both triage startup and reset)"

requirements-completed: [CLOSE-01]

# Metrics
duration: 3min
completed: 2026-03-05
---

# Phase 15 Plan 01: Audit Fixes Summary

**Fixed infrastructure_groups consistency in reset path, eliminated structlog test cross-contamination, removed 2 dead production methods and 5 dead test classes, aligned RTRI-04 requirement wording**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-05T00:28:22Z
- **Completed:** 2026-03-05T00:32:10Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Fixed validate_groups call in resetter.py to include infrastructure_groups kwarg, matching the triage startup path
- Added configure_logging mock in test_resetter.py to prevent structlog cross-contamination (96 failures in full suite)
- Removed dead production methods: _get_destination_mailbox_ids (screener.py) and batch_move_emails (jmap.py)
- Removed 5 dead test classes (20 tests) that tested the removed methods
- Updated RTRI-04 requirement wording to match actual code behavior ("Triaged to" / "Re-triaged to")

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix infrastructure_groups consistency and structlog cross-contamination** - `1bf072f` (fix)
2. **Task 2: Remove dead code and update REQUIREMENTS.md** - `67d299f` (chore)

## Files Created/Modified
- `src/mailroom/reset/resetter.py` - Added infrastructure_groups kwarg to validate_groups call
- `tests/test_resetter.py` - Added configure_logging mock to prevent structlog cross-contamination
- `src/mailroom/workflows/screener.py` - Removed dead _get_destination_mailbox_ids method (~20 lines)
- `src/mailroom/clients/jmap.py` - Removed dead batch_move_emails method (~55 lines)
- `tests/test_screener_workflow.py` - Removed 4 dead test classes (TestGetDestinationMailboxIds, TestToPersonDestinationMailbox, TestAddToInboxNotInherited, TestRootCategoryAddToInbox), updated stale mock assertion
- `tests/test_jmap_client.py` - Removed dead TestBatchMoveEmails test class
- `.planning/REQUIREMENTS.md` - Updated RTRI-04 wording to match code

## Decisions Made
- Replaced `jmap.batch_move_emails.assert_not_called()` with `jmap.call.assert_not_called()` since the production method was removed (MagicMock would still auto-create the attribute, but the assertion would be testing dead behavior)
- Updated docstring mentioning batch_move_emails to remove dead code reference

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated stale batch_move_emails mock assertion**
- **Found during:** Task 2 (Remove dead code)
- **Issue:** test_screener_workflow.py had `jmap.batch_move_emails.assert_not_called()` referencing the removed method, plus a docstring mention
- **Fix:** Changed assertion to `jmap.call.assert_not_called()` (tests JMAP call layer, not removed method); updated docstring
- **Files modified:** tests/test_screener_workflow.py
- **Verification:** Full test suite passes (407 tests)
- **Committed in:** 67d299f (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Auto-fix necessary to achieve "zero grep hits" verification criteria. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All audit code/test issues resolved
- Plan 15-02 (documentation finalization) can proceed independently
- Full test suite green at 407 tests

## Self-Check: PASSED

All files exist, all commits verified, all verification criteria met.

---
*Phase: 15-milestone-closeout-cleanup*
*Completed: 2026-03-05*
