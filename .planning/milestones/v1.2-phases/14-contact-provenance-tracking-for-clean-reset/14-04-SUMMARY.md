---
phase: 14-contact-provenance-tracking-for-clean-reset
plan: 04
subsystem: reset
tags: [jmap, carddav, rfc8621, etag, reset]

# Dependency graph
requires:
  - phase: 14-03
    provides: "Provenance-aware reset with 7-step operation order"
provides:
  - "Working apply_reset that moves emails to Screener before label removal"
  - "Step 6 skips delete targets to preserve ETags for step 7"
affects: [14-UAT, reset]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Move pattern: add destination mailbox before removing source (RFC 8621 compliance)"
    - "Skip-then-delete: don't modify resources you're about to delete"

key-files:
  created: []
  modified:
    - src/mailroom/reset/resetter.py
    - tests/test_resetter.py

key-decisions:
  - "Step 1 adds Screener before removing managed labels (atomic move pattern for RFC 8621 compliance)"
  - "Step 6 skips contacts_to_delete entirely rather than capturing returned ETags (simpler, more correct)"

patterns-established:
  - "RFC 8621 compliance: always ensure emails have at least one mailbox before removing labels"

requirements-completed: [PROV-10, PROV-11]

# Metrics
duration: 4min
completed: 2026-03-04
---

# Phase 14 Plan 04: Gap Closure - Reset Apply Bugs Summary

**Fix two blocker bugs in apply_reset: JMAP RFC 8621 mailbox violation and 412 stale ETag on contact DELETE**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-04T18:57:26Z
- **Completed:** 2026-03-04T19:01:17Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Step 1 now moves emails to Screener mailbox before removing managed labels, preventing RFC 8621 violation (emails must belong to >=1 mailbox)
- Step 6 no longer processes contacts_to_delete, so step 7 DELETE uses original valid ETags
- 7-step operation order preserved with new add-Screener calls tracked separately
- All 417 tests pass including 32 resetter-specific tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix step 1 JMAP label removal** - `86922ef` (test: RED), `afa230a` (feat: GREEN)
2. **Task 2: Fix stale ETag bug in step 6** - `d85d6b5` (test: RED), `d044edd` (fix: GREEN)

_TDD tasks have two commits each (test then implementation)_

## Files Created/Modified
- `src/mailroom/reset/resetter.py` - Fixed step 1 (add Screener before remove label) and step 6 (skip delete targets)
- `tests/test_resetter.py` - New tests for Screener move pattern and step 6 skip behavior, updated existing tests

## Decisions Made
- Step 1 adds Screener before removing managed labels (atomic move pattern): simpler than checking current mailbox membership per-email. Screener mailbox is NOT a triage trigger, so this won't cause re-triage.
- Step 6 skips contacts_to_delete entirely: simpler fix than capturing and propagating ETags from update_contact_vcard return values. Why strip notes from contacts about to be deleted?

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- apply_reset now completes without errors for all email/contact configurations
- Ready for UAT re-test (human-test 8: reset --apply)

## Self-Check: PASSED

All files exist, all commits verified (86922ef, afa230a, d85d6b5, d044edd).

---
*Phase: 14-contact-provenance-tracking-for-clean-reset*
*Completed: 2026-03-04*
