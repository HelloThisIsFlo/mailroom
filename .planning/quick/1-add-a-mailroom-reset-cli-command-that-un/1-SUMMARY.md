---
phase: quick-1
plan: 1
subsystem: reset
tags: [cli, reset, carddav, jmap, contacts, labels, groups]
dependency_graph:
  requires: [carddav-client, jmap-client, config, setup-colors]
  provides: [reset-module, reset-cli-command]
  affects: [cli.py, carddav.py, jmap.py]
tech_stack:
  added: []
  patterns: [dry-run/apply, terraform-style-reporting, tdd]
key_files:
  created:
    - src/mailroom/reset/__init__.py
    - src/mailroom/reset/resetter.py
    - src/mailroom/reset/reporting.py
    - tests/test_resetter.py
  modified:
    - src/mailroom/cli.py
    - src/mailroom/clients/carddav.py
    - src/mailroom/clients/jmap.py
decisions:
  - Used get_group_members() public method instead of reaching into CardDAV internals for group membership queries
  - Contacts NOT deleted, only Mailroom note section stripped (preserving pre-existing content)
  - Screener and Inbox excluded from managed label cleanup
metrics:
  duration: 4min
  completed: "2026-03-04T12:13:36Z"
---

# Quick Task 1: Add Mailroom Reset CLI Command Summary

Reset CLI command that undoes all Mailroom changes: strips Mailroom notes from contacts, removes managed labels from emails, empties managed contact groups via dry-run/apply pattern.

## What Was Built

### New Files

- **`src/mailroom/reset/resetter.py`** -- Core reset logic with `plan_reset()`, `apply_reset()`, and `run_reset()`. Builds a `ResetPlan` dataclass identifying emails in managed labels, group memberships, and annotated contacts. Executes cleanup in strict order: labels first, then groups, then contact notes.

- **`src/mailroom/reset/reporting.py`** -- Terraform-style output with sections for email labels, contact groups, contacts to clean, and a separate "Likely Mailroom-Created Contacts" section flagging contacts for manual deletion.

- **`tests/test_resetter.py`** -- 14 unit tests covering plan building (annotated contact identification, Screener/Inbox exclusion, likely-created detection), apply execution (operation order, label removal, group emptying, note stripping for both mailroom-only and mixed notes), and reporting output.

### Modified Files

- **`src/mailroom/clients/carddav.py`** -- Added `list_all_contacts()` (fetches all non-group vCards), `update_contact_vcard()` (PUT with If-Match), and `get_group_members()` (extracts member UIDs from group vCard).

- **`src/mailroom/clients/jmap.py`** -- Added `batch_remove_labels()` for batch email label removal using Email/set patch syntax in BATCH_SIZE chunks.

- **`src/mailroom/cli.py`** -- Added `reset` command with `--apply` flag, following the exact pattern of the existing `setup` command.

### Key Behaviors

1. `python -m mailroom reset` -- Dry-run showing what would be cleaned
2. `python -m mailroom reset --apply` -- Executes all cleanup operations
3. Contacts are NOT deleted, only their Mailroom note section is stripped
4. Pre-existing note content before the Mailroom header is preserved
5. Screener mailbox is untouched (excluded from managed labels)
6. Managed labels and groups remain but their contents are emptied
7. Likely-created contacts flagged separately (mailroom-only note + only managed group memberships)
8. Operation order: (1) remove labels, (2) remove group members, (3) strip notes

## Commits

| # | Hash | Message |
|---|------|---------|
| 1 | bf26cca | test(quick-1): add failing tests for reset module |
| 2 | c08f39e | feat(quick-1): implement reset module with client methods and tests |
| 3 | 99df779 | feat(quick-1): wire reset command to CLI |

## Verification Results

1. `python -m pytest tests/test_resetter.py -x -v` -- 14/14 passed
2. `python -m pytest tests/ -x -q` -- 376/376 passed (no regressions)
3. `python -m mailroom reset --help` -- Shows help text
4. `python -m mailroom --help` -- Shows reset alongside setup and run

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added get_group_members() method to CardDAVClient**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Plan specified reaching into CardDAV internals (`carddav._http.get()` + vobject parsing) to check group membership, which made unit testing brittle and violated encapsulation
- **Fix:** Added a public `get_group_members(group_name)` method to CardDAVClient that returns member UIDs, used by resetter instead of internal access
- **Files modified:** `src/mailroom/clients/carddav.py`, `src/mailroom/reset/resetter.py`
- **Commit:** c08f39e

## Self-Check: PASSED

All 7 files verified present. All 3 commits verified in git log.
