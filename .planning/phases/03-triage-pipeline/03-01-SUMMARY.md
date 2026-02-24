---
phase: 03-triage-pipeline
plan: 01
subsystem: workflow
tags: [jmap, carddav, triage, conflict-detection, structlog, polling]

# Dependency graph
requires:
  - phase: 01-foundation-and-jmap-client
    provides: JMAPClient with query_emails, get_email_senders, call, remove_label, batch_move_emails
  - phase: 02-carddav-client-validation-gate
    provides: CardDAVClient with upsert_contact, add_to_group, validate_groups
provides:
  - ScreenerWorkflow class with poll cycle orchestration
  - Conflict detection splitting senders into clean/conflicted
  - @MailroomError additive labeling for conflicted senders
  - @MailroomError skip-filtering on already-errored emails
  - Config with screener_mailbox setting and destination_mailbox in mapping
  - _process_sender stub for Plan 02 to implement
affects: [03-02-PLAN, 04-packaging-and-deployment]

# Tech tracking
tech-stack:
  added: []
  patterns: [workflow-as-orchestrator, conflict-detection-before-mutation, error-label-as-pause-signal, retry-via-label-state]

key-files:
  created:
    - src/mailroom/workflows/screener.py
    - tests/test_screener_workflow.py
  modified:
    - src/mailroom/core/config.py
    - src/mailroom/workflows/__init__.py
    - tests/test_config.py
    - tests/conftest.py

key-decisions:
  - "poll() catches all exceptions from _process_sender via except Exception for retry safety (TRIAGE-06)"
  - "_apply_error_label wraps all JMAP calls in try/except to prevent transient failures from crashing poll cycle"
  - "Post-query @MailroomError filtering via Email/get with mailboxIds check (single JMAP call for all triaged emails)"
  - "destination_mailbox added to label_to_group_mapping for self-contained mapping (Imbox -> Inbox, others match group name)"

patterns-established:
  - "Workflow-as-orchestrator: ScreenerWorkflow calls client methods, contains zero protocol details"
  - "Conflict detection before mutation: _detect_conflicts runs before any _process_sender call"
  - "Error label additive: @MailroomError added via JMAP patch without removing triage labels"
  - "Label-as-state: triage labels removed only after full processing succeeds (retry safety)"

requirements-completed: [TRIAGE-01, TRIAGE-06]

# Metrics
duration: 4min
completed: 2026-02-24
---

# Phase 3 Plan 01: ScreenerWorkflow Poll Cycle Summary

**ScreenerWorkflow class with poll cycle orchestration, conflict detection, @MailroomError labeling, and retry-safe exception handling using mocked clients (21 tests)**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-24T11:29:33Z
- **Completed:** 2026-02-24T11:34:04Z
- **Tasks:** 3 (TDD: RED, GREEN, REFACTOR)
- **Files modified:** 6

## Accomplishments
- ScreenerWorkflow.poll() collects triaged emails across all 4 labels and groups by sender
- Conflicting triage labels (same sender, different labels) detected pre-mutation, @MailroomError applied additively
- Already-errored emails filtered out of collection via single Email/get call
- Transient failures in _apply_error_label and _process_sender do not crash poll cycle
- Config extended with screener_mailbox and destination_mailbox in label_to_group_mapping

## Task Commits

Each task was committed atomically (TDD red-green-refactor):

1. **RED: Failing tests** - `6c45e0f` (test)
2. **GREEN: Implementation** - `7bf4bf2` (feat)
3. **REFACTOR: Cleanup** - `a9d6a9f` (refactor)

## Files Created/Modified
- `src/mailroom/workflows/screener.py` - ScreenerWorkflow class with poll(), _collect_triaged(), _detect_conflicts(), _apply_error_label(), _process_sender() stub
- `tests/test_screener_workflow.py` - 21 tests covering all poll cycle scenarios with mocked JMAP/CardDAV clients
- `src/mailroom/core/config.py` - Added screener_mailbox setting, destination_mailbox in label_to_group_mapping
- `src/mailroom/workflows/__init__.py` - Updated module docstring
- `tests/test_config.py` - 3 new tests for screener_mailbox and destination_mailbox
- `tests/conftest.py` - Shared fixtures: mock_settings, mock_mailbox_ids

## Decisions Made
- poll() catches all exceptions from _process_sender (including NotImplementedError stub) via except Exception -- this is the retry safety mechanism per TRIAGE-06
- _apply_error_label wraps entire operation in try/except to prevent transient JMAP failures from crashing the poll cycle
- @MailroomError filtering uses post-query approach: single Email/get call with ["id", "mailboxIds"] properties, checking for error label ID in mailboxIds dict
- destination_mailbox added to config mapping for self-contained routing (Imbox -> Inbox mailbox, Feed/Paper Trail/Jail match group names)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Initial test expectations assumed NotImplementedError would propagate from poll(), but poll() correctly catches it via except Exception. Tests were adjusted to verify behavior through return values instead of exception propagation. This is correct behavior per TRIAGE-06 (retry safety).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- ScreenerWorkflow skeleton complete, ready for Plan 02 to implement _process_sender body
- Config has destination_mailbox mapping ready for sweep destination resolution
- _process_sender stub raises NotImplementedError as explicit marker for Plan 02
- All 86 tests in the suite pass (no regressions)

---
*Phase: 03-triage-pipeline*
*Completed: 2026-02-24*
