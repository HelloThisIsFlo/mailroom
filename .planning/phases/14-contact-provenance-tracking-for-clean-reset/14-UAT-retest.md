---
status: complete
phase: 14-contact-provenance-tracking-for-clean-reset
source: 14-04-SUMMARY.md, 14-05-SUMMARY.md
started: 2026-03-04T20:00:00Z
updated: 2026-03-04T20:30:00Z
note: Re-verification of gap closure fixes from plans 04 and 05
---

## Current Test

[testing complete]

## Tests

### 1. Config Rejects Old labels: Key Cleanly
expected: Change config to use `labels:` instead of `mailroom:`. Run mailroom. Should fail with a short, plain "unknown key" error listing valid keys. No migration guide, no backward-compat messaging.
result: pass

### 2. Reset Dry-Run Banner
expected: Run `python -m mailroom reset` (dry-run mode). Before any scanning output, a prominent banner appears: "DRY RUN — no changes will be made" (or similar). Progress messages visible during scan.
result: pass

### 3. Reset Apply Banner
expected: Run `python -m mailroom reset --apply`. Before any output, a prominent warning banner appears indicating APPLY mode (real changes). Progress messages visible during operations.
result: issue
reported: "Red banner shows but it just runs immediately. Should run dry-run first, show the plan, ask 'Are you okay with this?', then proceed with the destructive operation."
severity: major

### 4. Reset Apply — Emails Moved to Screener
expected: Run `python -m mailroom reset --apply` after triaging some emails. All managed labels removed from emails WITHOUT "unknown error". Emails end up in Screener (not orphaned without a mailbox). Check Screener folder has the emails.
result: pass
note: 1,310 emails across 7 labels (Billboard, Feed, Imbox, Jail, Paper Trail, Person, Truck) all moved to Screener successfully. Pre-existing orphaned emails from previous broken reset discovered (Doppler) — see .research/recover-corrupted-emails/

### 5. Reset Apply — Contact Deletion Succeeds
expected: After triage created contacts, run reset --apply. Unmodified Mailroom-created contacts are fully deleted. No 412 Precondition Failed errors. Reset completes all 7 steps.
result: pass
note: 5 contacts deleted cleanly (Shortform Recommendations, verify, James Shack, Amazon.co.uk, Zoom)

### 6. Reset Apply — Modified Contacts Get Warning
expected: Edit a Mailroom-created contact in Fastmail (change phone or name). Run reset --apply. That contact is NOT deleted — gets @MailroomWarning label instead. (This was skipped last UAT due to blocker.)
result: pass
note: Trading 212 (renamed to 2-1-3) correctly warned instead of deleted

### 7. Reset Apply — Adopted Contacts Stripped
expected: Run reset --apply. Adopted contacts (existing contacts that Mailroom added notes to) have Mailroom notes stripped but remain in contacts. No deletion. (This was skipped last UAT due to blocker.)
result: pass
note: 4 adopted contacts (The Keys Coach, Telepathic Instruments, Frive, Steam) stripped, remain in contacts

### 8. REV Field Human Test
expected: Run `python human-tests/test_18_rev_field_user_modification.py`. Test creates a contact, edits it via Fastmail CardDAV, and verifies the REV field changes — confirming _is_user_modified() detection works.
result: pass
note: All 4 checks passed. REV dependency documented in code (resetter.py:25-32), unit test (test_resetter.py:834-842), and human integration test (test_18)

## Summary

total: 8
passed: 7
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "Reset --apply asks for user confirmation before executing destructive operations"
  status: failed
  reason: "User reported: Red banner shows but it just runs immediately. Should run dry-run first, show the plan, ask 'Are you okay with this?', then proceed with the destructive operation."
  severity: major
  test: 3
  root_cause: "run_reset() in resetter.py:456-462 — when apply=True, it goes straight from plan_reset() to apply_reset() with no confirmation step. The dry-run report (print_reset_report with apply=False) is only shown when apply is False. Need to: always show the plan first, then prompt for confirmation when apply=True."
  artifacts:
    - path: "src/mailroom/reset/resetter.py"
      issue: "Lines 456-462: apply branch skips plan display and goes straight to apply_reset()"
    - path: "src/mailroom/reset/reporting.py"
      issue: "No confirmation prompt function exists"
  missing:
    - "When apply=True: show plan report first (same as dry-run), then prompt 'Proceed? [y/N]', then execute"
    - "Add print_confirmation_prompt() to reporting.py"
  debug_session: ""
