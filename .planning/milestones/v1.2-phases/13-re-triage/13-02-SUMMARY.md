---
phase: 13-re-triage
plan: 02
subsystem: workflow
tags: [re-triage, screener, contact-groups, email-reconciliation, chain-diff, structured-logging]

# Dependency graph
requires:
  - phase: 13-re-triage
    plan: 01
    provides: "CardDAV remove_from_group, JMAP query_emails_by_sender, get_email_mailbox_ids, triage history notes"
provides:
  - "Re-triage detection and execution in _process_sender"
  - "Contact group reassignment with chain diff (add-first-then-remove)"
  - "Full email label reconciliation (strip managed + Screener, apply new additive)"
  - "Structured group_reassigned logging event"
affects: [13-03-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Re-triage detection: _detect_retriage() returns (contact_uid, old_group) tuple"
    - "Chain diff for group reassignment: set difference between old/new parent chains"
    - "Email label reconciliation: strip all managed labels, apply new additive set"
    - "Inbox handling: location-based (Screener presence), never removed"

key-files:
  created: []
  modified:
    - src/mailroom/workflows/screener.py
    - tests/test_screener_workflow.py

key-decisions:
  - "Re-triage replaces already-grouped error path entirely (no @MailroomError for grouped senders)"
  - "Same-group re-triage runs full reconciliation for self-healing"
  - "Chain diff uses set operations on contact_group names for efficiency"
  - "Inbox never in managed_mailbox_ids removal set (explicit exclusion)"

patterns-established:
  - "Re-triage branch in _process_sender: detect -> upsert -> reassign groups -> reconcile labels -> log -> remove triage label"
  - "group_reassigned structured event with old_group, new_group, same_group, emails_reconciled fields"

requirements-completed: [RTRI-01, RTRI-02, RTRI-03, RTRI-06]

# Metrics
duration: 4min
completed: 2026-03-03
---

# Phase 13 Plan 02: Screener Workflow Re-triage Summary

**Re-triage detection with chain-diff group reassignment, full email label reconciliation, and structured group_reassigned logging replacing the already-grouped error path**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-03T23:30:44Z
- **Completed:** 2026-03-03T23:35:03Z
- **Tasks:** 1 (TDD: test + feat)
- **Files modified:** 2

## Accomplishments
- Replaced `_check_already_grouped()` with `_detect_retriage()` that finds ALL groups (no exclude_group)
- Added `_reassign_contact_groups()` with chain diff: add new-only groups FIRST, then remove old-only (safe partial-failure order)
- Added `_reconcile_email_labels()` that strips ALL managed destination labels + Screener, applies new additive labels in BATCH_SIZE chunks
- Rewrote `_process_sender()` to branch on is_retriage vs initial triage with full backward compatibility
- Inbox is never removed; only added to emails currently in Screener when add_to_inbox is True
- Structured `group_reassigned` log event with old_group, new_group, same_group, emails_reconciled fields
- Same-group re-triage runs full reconciliation for self-healing (chain diff produces empty add/remove sets)
- @MailroomError is no longer applied for already-grouped senders
- All 359 tests passing (15 new tests added, 3 test classes renamed/updated)

## Task Commits

Each task was committed atomically (TDD: test -> feat):

1. **Task 1: Re-triage detection and workflow logic in _process_sender**
   - `5c93817` (test: failing tests for re-triage workflow)
   - `63cbb9a` (feat: implement re-triage workflow in _process_sender)

## Files Created/Modified
- `src/mailroom/workflows/screener.py` - Replaced _check_already_grouped with _detect_retriage, added _reassign_contact_groups and _reconcile_email_labels, rewrote _process_sender
- `tests/test_screener_workflow.py` - Renamed TestAlreadyGrouped* to TestRetriage*, added 6 new test classes (chain diff, add-before-remove, label reconciliation, inbox Screener-only, structured logging, initial triage unchanged)

## Decisions Made
- Re-triage replaces the already-grouped error path entirely -- @MailroomError is no longer applied when a sender is already in a contact group
- Same-group re-triage runs the full reconciliation path (self-healing) with chain diff producing empty sets (no-op for group changes)
- Chain diff uses set operations on contact_group names from get_parent_chain results
- Inbox is explicitly excluded from the managed_mailbox_ids removal set (never removed during reconciliation)
- `_detect_retriage` calls `check_membership()` without `exclude_group` to find ALL groups including same-group

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Re-triage workflow complete, ready for human integration tests (Plan 03)
- All client methods (Plan 01) and workflow logic (Plan 02) integrated and tested
- Plan 03 can implement human test test_17_retriage.py and update test_9_already_grouped.py

---
*Phase: 13-re-triage*
*Completed: 2026-03-03*
