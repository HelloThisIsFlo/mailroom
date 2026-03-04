---
phase: 14-contact-provenance-tracking-for-clean-reset
plan: 02
subsystem: carddav, screener
tags: [carddav, provenance, contact-groups, warning-cleanup, vcard-notes]

# Dependency graph
requires:
  - phase: 14-contact-provenance-tracking-for-clean-reset
    provides: MailroomSectionSettings with provenance_group field, provisioner creates provenance group
provides:
  - infrastructure_groups exclusion in check_membership (provenance invisible to triage)
  - provenance_group parameter on upsert_contact (add to provenance group on creation only)
  - "Created by Mailroom" and "Adopted by Mailroom" provenance note lines
  - "@MailroomWarning cleanup on every successful triage (remove then conditionally reapply)"
affects: [14-03, reset, human-tests]

# Tech tracking
tech-stack:
  added: []
  patterns: [infrastructure_groups exclusion set, warning cleanup-then-reapply pattern]

key-files:
  created: []
  modified:
    - src/mailroom/clients/carddav.py
    - src/mailroom/workflows/screener.py
    - src/mailroom/__main__.py
    - tests/test_carddav_client.py
    - tests/test_screener_workflow.py

key-decisions:
  - "infrastructure_groups stored as set on CardDAVClient, populated via validate_groups param"
  - "Provenance note: 'Created by Mailroom' for new contacts, 'Adopted by Mailroom' for existing contacts without Mailroom note"
  - "Re-triage of already-tracked contacts appends triage entry without duplicate provenance line"
  - "Warning cleanup uses query_emails_by_sender + batch_remove_labels before upsert"

patterns-established:
  - "Infrastructure groups: validate_groups(infrastructure_groups=[...]) excludes groups from check_membership"
  - "Warning cleanup-then-reapply: remove @MailroomWarning before processing, reapply if condition persists"
  - "Provenance notes: Created/Adopted provenance line between header and triage entry"

requirements-completed: [PROV-04, PROV-05, PROV-06, PROV-07]

# Metrics
duration: 11min
completed: 2026-03-04
---

# Phase 14 Plan 02: CardDAV Provenance Tracking + Warning Cleanup Summary

**CardDAV provenance group membership on contact creation, "Created/Adopted by Mailroom" note format, infrastructure_groups exclusion from triage detection, and @MailroomWarning cleanup on every successful triage**

## Performance

- **Duration:** 11 min
- **Started:** 2026-03-04T14:34:49Z
- **Completed:** 2026-03-04T14:45:49Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- New contacts added to provenance group on creation; existing contacts are NOT added (creation-only behavior)
- Contact notes include "Created by Mailroom" (new) or "Adopted by Mailroom" (existing without prior Mailroom note)
- check_membership() skips infrastructure groups (provenance group invisible to triage/re-triage detection)
- @MailroomWarning removed from all sender emails before every triage; reapplied only if name mismatch persists
- Provenance group name flows from settings through screener to upsert_contact

## Task Commits

Each task was committed atomically:

1. **Task 1: CardDAV provenance -- infrastructure_groups, provenance note format, provenance group membership** - `6c23be0` (feat)
2. **Task 2: Screener @MailroomWarning cleanup + provenance_group plumbing** - `b1d9863` (feat)

## Files Created/Modified
- `src/mailroom/clients/carddav.py` - Added infrastructure_groups set, infrastructure_groups param on validate_groups, exclusion in check_membership, "Created by Mailroom" in create_contact, provenance_group param on upsert_contact, "Adopted by Mailroom" for existing contacts
- `src/mailroom/workflows/screener.py` - Added @MailroomWarning cleanup step before upsert, provenance_group plumbing to upsert_contact
- `src/mailroom/__main__.py` - Passes infrastructure_groups to validate_groups at startup
- `tests/test_carddav_client.py` - 11 new tests for provenance behavior, updated 5 existing tests for new note format
- `tests/test_screener_workflow.py` - 5 new tests for warning cleanup and provenance plumbing, updated ~20 existing tests for provenance_group kwarg and query_emails_by_sender call count

## Decisions Made
- infrastructure_groups stored as a set on CardDAVClient, populated via validate_groups param (not constructor)
- Provenance note lines: "Created by Mailroom" for new contacts, "Adopted by Mailroom" for existing contacts without Mailroom note
- Re-triage of already-tracked contacts (with existing Mailroom note header) just appends triage entry -- no duplicate provenance line
- Warning cleanup uses existing query_emails_by_sender + batch_remove_labels (extra JMAP call per sender is negligible)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing test expectations for new note format**
- **Found during:** Task 1 (CardDAV provenance note format)
- **Issue:** 5 existing create_contact and upsert_contact tests expected old note format without "Created by Mailroom" and "Adopted by Mailroom" lines
- **Fix:** Updated test assertions to match new note format
- **Files modified:** tests/test_carddav_client.py
- **Verification:** All 60 CardDAV tests pass
- **Committed in:** 6c23be0 (Task 1 commit)

**2. [Rule 1 - Bug] Updated existing screener test assertions for provenance_group kwarg**
- **Found during:** Task 2 (Screener provenance plumbing)
- **Issue:** ~13 existing assert_called_once_with tests for upsert_contact did not include provenance_group="Mailroom" kwarg; ~9 assert_called_once_with for query_emails_by_sender failed because it is now called twice (cleanup + reconciliation)
- **Fix:** Added provenance_group="Mailroom" to all upsert_contact assertions; changed query_emails_by_sender to assert_any_call; updated step order test for new cleanup step
- **Files modified:** tests/test_screener_workflow.py
- **Verification:** All 143 screener tests pass
- **Committed in:** b1d9863 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs -- test expectation updates for intentional behavior changes)
**Impact on plan:** Both auto-fixes necessary for correctness after intentional behavior changes. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Provenance tracking fully operational in CardDAV client and screener pipeline
- Provenance group created at setup (Plan 01), contacts tracked on creation (Plan 02)
- Ready for Plan 03 (reset command with provenance-based cleanup)

## Self-Check: PASSED

All files exist. All commits verified (6c23be0, b1d9863). Full test suite: 395 passed.

---
*Phase: 14-contact-provenance-tracking-for-clean-reset*
*Completed: 2026-03-04*
