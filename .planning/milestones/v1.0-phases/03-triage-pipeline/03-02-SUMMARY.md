---
phase: 03-triage-pipeline
plan: 02
subsystem: workflow
tags: [jmap, carddav, triage, sweep, destination-mapping, idempotent, already-grouped-check, structlog]

# Dependency graph
requires:
  - phase: 03-triage-pipeline
    plan: 01
    provides: ScreenerWorkflow class with poll cycle, conflict detection, _process_sender stub
  - phase: 01-foundation-and-jmap-client
    provides: JMAPClient with query_emails, batch_move_emails, remove_label
  - phase: 02-carddav-client-validation-gate
    provides: CardDAVClient with upsert_contact, add_to_group, search_by_email, validate_groups
provides:
  - Complete _process_sender pipeline (already-grouped check -> upsert -> sweep -> remove label)
  - _get_destination_mailbox_ids helper for label-to-mailbox resolution
  - _check_already_grouped for sender group conflict detection
  - CardDAVClient.check_membership for group membership verification
  - Full per-sender triage flow with all 4 destination types
affects: [04-packaging-and-deployment]

# Tech tracking
tech-stack:
  added: []
  patterns: [strict-step-ordering, already-grouped-check-during-processing, destination-mailbox-resolution]

key-files:
  created: []
  modified:
    - src/mailroom/workflows/screener.py
    - src/mailroom/clients/carddav.py
    - tests/test_screener_workflow.py

key-decisions:
  - "_check_already_grouped runs during per-sender processing (not pre-mutation gate) to handle CardDAV transient failures via retry"
  - "CardDAVClient.check_membership added as public method to keep protocol logic in the client (not workflow)"
  - "Destination mailbox resolved via config's destination_mailbox field (Imbox->Inbox, others match group name)"
  - "Empty sweep (no emails found) still removes triage label -- sweep query always executes per user decision"

patterns-established:
  - "Strict step ordering: already-grouped check -> upsert -> sweep -> remove label (remove is always last)"
  - "Already-grouped check only for existing contacts (new senders skip membership check entirely)"
  - "Destination resolution via config mapping: label -> destination_mailbox -> mailbox_id"

requirements-completed: [TRIAGE-02, TRIAGE-03, TRIAGE-04, TRIAGE-05]

# Metrics
duration: 4min
completed: 2026-02-24
---

# Phase 3 Plan 02: Per-Sender Triage Processing Summary

**Complete _process_sender pipeline with strict-order upsert/sweep/relabel, already-grouped detection via CardDAV check_membership, and all 4 destination types (39 new tests)**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-24T11:37:13Z
- **Completed:** 2026-02-24T11:41:58Z
- **Tasks:** 3 (TDD: RED, GREEN, REFACTOR)
- **Files modified:** 3

## Accomplishments
- _process_sender implements full triage pipeline: already-grouped check, contact upsert, email sweep, destination move, triage label removal (strict order)
- All 4 destination types working: Imbox (adds Inbox label), Feed, Paper Trail, Jail (add their mailbox labels)
- Already-grouped sender in different group triggers @MailroomError and stops processing; same group proceeds normally (idempotent)
- CardDAVClient.check_membership method checks contact UID against all validated groups with exclude parameter
- Transient failures at any step leave triage labels in place for retry on next poll cycle

## Task Commits

Each task was committed atomically (TDD red-green-refactor):

1. **RED: Failing tests** - `ef7b7e4` (test)
2. **GREEN: Implementation** - `1585f5f` (feat)
3. **REFACTOR: Cleanup** - `72170a5` (refactor)

## Files Created/Modified
- `src/mailroom/workflows/screener.py` - Replaced _process_sender stub with full implementation, added _get_destination_mailbox_ids and _check_already_grouped
- `src/mailroom/clients/carddav.py` - Added check_membership method for group membership verification
- `tests/test_screener_workflow.py` - 39 new tests covering all destination types, step ordering, already-grouped detection, error handling, and poll integration

## Decisions Made
- _check_already_grouped runs during per-sender processing (not in the pre-mutation conflict detection gate) so CardDAV transient failures are handled by the retry mechanism (per research Pitfall 5)
- CardDAVClient.check_membership added as a public method to keep CardDAV protocol logic in the client rather than the workflow
- Destination mailbox resolution uses the config's destination_mailbox field directly -- no special-case logic in the workflow
- Empty sweep results still proceed to triage label removal (sweep query always executes per user decision)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 3 complete: full triage pipeline with poll cycle, conflict detection, per-sender processing
- ScreenerWorkflow is ready to be wrapped in a polling loop (Phase 4)
- All 125 tests pass (60 workflow + 65 other) with zero regressions
- Requirements TRIAGE-01 through TRIAGE-06 all covered between Plans 01 and 02

## Self-Check: PASSED

- All 3 modified/created files verified on disk
- All 3 task commits verified in git history (ef7b7e4, 1585f5f, 72170a5)
- SUMMARY.md created and verified

---
*Phase: 03-triage-pipeline*
*Completed: 2026-02-24*
