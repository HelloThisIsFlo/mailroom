---
phase: quick-1
verified: 2026-03-04T12:30:00Z
status: passed
score: 6/6 must-haves verified
re_verification: false
---

# Quick Task 1: Add Mailroom Reset CLI Command — Verification Report

**Task Goal:** Add a mailroom reset CLI command that undoes all mailroom changes (contacts, labels, groups) with dry-run/apply mode
**Verified:** 2026-03-04T12:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                                   | Status     | Evidence                                                                                    |
|----|---------------------------------------------------------------------------------------------------------|------------|---------------------------------------------------------------------------------------------|
| 1  | Running `python -m mailroom reset` shows a dry-run report of contacts to clean, emails to un-label, and group memberships to remove | VERIFIED | `cli.py` wires reset command with `run_reset(apply=False)` default; `reporting.py` prints all three sections; `python -m mailroom reset --help` confirms command exists |
| 2  | Running `python -m mailroom reset --apply` executes all cleanup operations                              | VERIFIED   | `--apply` flag present in CLI; `apply_reset()` fully implemented in `resetter.py`; `run_reset()` branches correctly on `apply` param |
| 3  | Contacts with Mailroom notes have the note section stripped but are NOT deleted                         | VERIFIED   | `apply_reset()` Step 3 parses vCard, strips note via `_strip_mailroom_note()`, PUTs via `update_contact_vcard()`; no delete calls present |
| 4  | All managed labels are removed from emails (triage labels, destination labels, error/warning labels) but Screener is untouched | VERIFIED   | `_get_managed_mailbox_names()` explicitly excludes `settings.triage.screener_mailbox` and "Inbox"; `batch_remove_labels()` implemented; test `test_excludes_screener_and_inbox` passes |
| 5  | All members are removed from managed contact groups but the groups themselves remain                    | VERIFIED   | `apply_reset()` Step 2 calls `remove_from_group()` per member UID (not delete-group); `test_group_emptying_calls` passes with 3 calls for 3 members |
| 6  | Likely-created contacts are flagged separately in the report for manual deletion                        | VERIFIED   | `ContactCleanup.likely_created` flag set in `plan_reset()`; reporting separates them under "Likely Mailroom-Created Contacts" section with manual deletion advisory; `test_likely_created_section` passes |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact                                | Expected                              | Status     | Details                                                              |
|-----------------------------------------|---------------------------------------|------------|----------------------------------------------------------------------|
| `src/mailroom/reset/resetter.py`        | Reset planning and execution logic    | VERIFIED   | Exports `run_reset`, `plan_reset`, `apply_reset`; 310 lines, substantive |
| `src/mailroom/reset/reporting.py`       | Reset report formatting               | VERIFIED   | Exports `print_reset_report`; terraform-style sections implemented   |
| `src/mailroom/cli.py`                   | CLI entry point with reset command    | VERIFIED   | Contains `def reset` at line 41 with `--apply` flag                  |
| `tests/test_resetter.py`               | Unit tests for reset logic            | VERIFIED   | 474 lines (min 80); 14 tests — TestPlanReset, TestApplyReset, TestResetReporting |

### Key Link Verification

| From                               | To                                  | Via                                         | Status     | Details                                                         |
|------------------------------------|-------------------------------------|---------------------------------------------|------------|-----------------------------------------------------------------|
| `src/mailroom/cli.py`              | `src/mailroom/reset/resetter.py`    | cli reset command imports run_reset         | WIRED      | Pattern `from mailroom.reset.resetter import run_reset` found at line 43 (lazy import in command body) |
| `src/mailroom/reset/resetter.py`   | `src/mailroom/clients/jmap.py`      | queries emails by label, batch removes labels | WIRED    | `jmap.query_emails(mb_id)` at line 100; `jmap.batch_remove_labels(email_ids, [mb_id])` at line 196 |
| `src/mailroom/reset/resetter.py`   | `src/mailroom/clients/carddav.py`   | lists all contacts, strips notes, removes from groups | WIRED | `carddav.list_all_contacts()` at line 105; `carddav.remove_from_group(group_name, uid)` at line 206 |

### Requirements Coverage

| Requirement | Source Plan | Description                             | Status    | Evidence                                        |
|-------------|-------------|-----------------------------------------|-----------|-------------------------------------------------|
| RESET-01    | quick-1     | Reset CLI command with dry-run/apply    | SATISFIED | Full implementation verified; all 4 verification commands from plan pass |

### Anti-Patterns Found

None. No TODO/FIXME/placeholder comments found in any new or modified files.

### Human Verification Required

#### 1. End-to-End Dry-Run Against Real Fastmail

**Test:** With real credentials configured, run `python -m mailroom reset`
**Expected:** Displays report of actual managed labels with email counts, group memberships, and annotated contacts
**Why human:** Requires live Fastmail credentials; verifies real JMAP/CardDAV responses are parsed correctly

#### 2. End-to-End Apply Against Real Fastmail

**Test:** After running setup to create state, run `python -m mailroom reset --apply`
**Expected:** Emails un-labeled, group members removed, contact notes stripped; subsequent dry-run shows 0 items
**Why human:** Requires live credentials and pre-seeded state; verifies the full cleanup cycle

### Gaps Summary

No gaps found. All 6 observable truths are satisfied by the implementation. The two human verification items are operational/integration tests that require live credentials and are not blocking — the unit tests cover all logic paths thoroughly (14/14 passing, 376/376 full suite passing).

---

_Verified: 2026-03-04T12:30:00Z_
_Verifier: Claude (gsd-verifier)_
