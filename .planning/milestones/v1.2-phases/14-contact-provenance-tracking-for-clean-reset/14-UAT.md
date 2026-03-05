---
status: resolved
phase: 14-contact-provenance-tracking-for-clean-reset
source: 14-01-SUMMARY.md, 14-02-SUMMARY.md, 14-03-SUMMARY.md
started: 2026-03-04T15:14:57Z
updated: 2026-03-04T15:45:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running mailroom process. Start fresh with `python -m mailroom`. Boots without errors, provisioning completes (including provenance group), startup validation passes.
result: pass

### 2. Config Migration Rejection
expected: Temporarily change your config to use the old `labels:` key instead of `mailroom:`. Running mailroom should fail with a clear error message telling you to rename `labels:` to `mailroom:`.
result: issue
reported: "Error message is too helpful — provides a full migration guide. Should just reject as unknown key with a clear error, no backward compatibility code."
severity: minor

### 3. Provenance Group Provisioned at Setup
expected: After running setup, the provenance contact group (default "Mailroom") exists in Fastmail contacts.
result: pass

### 4. New Contact Added to Provenance Group
expected: Triage a new unknown sender. After triage, the new contact appears in the provenance contact group.
result: pass

### 5. Provenance Note on Created Contact
expected: Created contacts have "Created by Mailroom" in notes. Adopted contacts have "Adopted by Mailroom". Adopted contacts are NOT in provenance group.
result: pass

### 6. Warning Cleanup on Successful Triage
expected: @MailroomWarning labels removed before triage; reapplied only if condition persists.
result: pass

### 7. Provenance-Aware Reset Report
expected: Reset report shows three distinct sections: DELETE, WARN, strip. No old "Likely Mailroom-Created" hints.
result: issue
reported: "Report output is beautiful and correct. Two UX issues: (1) No progress indication during long-running reset — at minimum a 'this may take a moment' message, ideally a Click progress bar. (2) Dry-run mode not crystal clear — needs a prominent banner upfront saying 'DRY RUN — no changes will be made' before any output, and a strong warning banner in apply mode."
severity: minor

### 8. Reset Deletes Unmodified Created Contacts
expected: Run reset in apply mode. Unmodified Mailroom-created contacts should be fully deleted.
result: issue
reported: "Reset failed halfway. Two errors: (1) JMAP label removal 'unknown error' on many emails across Feed, Jail, Paper Trail. (2) Contact deletion 412 Precondition Failed — step 6 strips notes (changing ETag) then step 7 tries to delete with stale ETag."
severity: blocker

### 9. Reset Warns Modified Created Contacts
expected: Modified Mailroom-created contacts get @MailroomWarning instead of deletion.
result: skipped
reason: Reset failed with errors in test 8; could not reliably verify.

### 10. Reset Strips Adopted Contacts
expected: Adopted contacts have Mailroom notes stripped but remain in contacts.
result: skipped
reason: Reset failed with errors in test 8; could not reliably verify.

## Summary

total: 10
passed: 5
issues: 3
pending: 0
skipped: 2

## Gaps

- truth: "Old labels: config key rejected with plain error"
  status: resolved
  reason: "User reported: Error message is too helpful — provides a full migration guide. Should just reject as unknown key, no backward compatibility code."
  severity: minor
  test: 2
  root_cause: "reject_old_labels_key validator in config.py already has a plain 2-sentence message. Agent found it's not as verbose as initially perceived. May just need slight simplification."
  artifacts:
    - path: "src/mailroom/core/config.py"
      issue: "reject_old_labels_key validator message mentions renaming — could be simpler"
  missing:
    - "Simplify error to just reject unknown key without mentioning migration"
  debug_session: ""

- truth: "Reset provides progress feedback and clear dry-run/apply mode indication"
  status: resolved
  reason: "User reported: No progress indication during long reset. Dry-run mode not prominent enough — needs upfront banner."
  severity: minor
  test: 7
  root_cause: "run_reset() in resetter.py has zero progress output between validation and final report. cli.py receives --apply flag but never displays mode. User sees nothing for 30-120 seconds."
  artifacts:
    - path: "src/mailroom/reset/resetter.py"
      issue: "run_reset() lines 376-446: no progress output; plan_reset() and apply_reset() execute silently"
    - path: "src/mailroom/reset/reporting.py"
      issue: "Only end-of-execution reporting; no upfront banner or progress functions"
    - path: "src/mailroom/cli.py"
      issue: "Lines 40-46: --apply flag passed silently to run_reset()"
  missing:
    - "Add upfront mode banner (DRY RUN / APPLY) before any execution"
    - "Add progress indication during plan and apply phases"
  debug_session: ""

- truth: "Fastmail adds REV field on contact edit — user-modification detection depends on this implicitly"
  status: resolved
  reason: "User reported: Happy accident that REV field triggers _is_user_modified(). Any undocumented relied-upon behavior is a major gap. Needs explicit test and human integration test validating Fastmail adds REV on edit."
  severity: major
  test: 8
  root_cause: "_is_user_modified() uses allowlist (MAILROOM_MANAGED_FIELDS). REV not in allowlist, so Fastmail UI edits trigger detection via REV timestamp field. Works but undocumented and untested."
  artifacts:
    - path: "src/mailroom/reset/resetter.py"
      issue: "Lines 24-59: MAILROOM_MANAGED_FIELDS and _is_user_modified() lack REV documentation"
    - path: "tests/test_resetter.py"
      issue: "TestIsUserModified has 9 tests but none for REV field"
  missing:
    - "Add unit test: test_rev_field_alone_returns_true"
    - "Add human integration test: test_18_rev_field_user_modification.py"
    - "Add code comments documenting REV dependency"
  debug_session: ""

- truth: "JMAP batch label removal succeeds for all emails during reset"
  status: resolved
  reason: "User reported: JMAP label removal returns 'unknown error' for many emails across Feed, Jail, Paper Trail during reset --apply"
  severity: blocker
  test: 8
  root_cause: "RFC 8621 requires emails belong to at least one mailbox. Emails triaged to Feed/Jail/Paper Trail (no add_to_inbox) have only that destination mailbox. batch_remove_labels removes it, leaving empty mailboxIds — Fastmail rejects."
  artifacts:
    - path: "src/mailroom/clients/jmap.py"
      issue: "batch_remove_labels (lines 421-467) has no guard against removing last mailbox"
    - path: "src/mailroom/reset/resetter.py"
      issue: "apply_reset Step 1 (lines 286-293) removes labels independently without awareness of email mailbox state"
  missing:
    - "Change Step 1 to MOVE emails back to Inbox instead of just removing labels (atomic add Inbox + remove managed label in single JMAP Email/set call)"
  debug_session: ".planning/debug/jmap-unknown-error-batch-label-removal.md"

- truth: "Contact deletion succeeds after note stripping in 7-step reset order"
  status: resolved
  reason: "User reported: 412 Precondition Failed — step 6 strips notes (changing ETag) then step 7 tries to delete with stale ETag"
  severity: blocker
  test: 8
  root_cause: "Step 6 builds all_contacts including contacts_to_delete. update_contact_vcard returns new ETag but return value is discarded. Step 7 calls delete_contact with original plan-time ETag which is now stale."
  artifacts:
    - path: "src/mailroom/reset/resetter.py"
      issue: "Line 340: all_contacts includes contacts_to_delete. Line 358: new ETag from update discarded. Line 368: delete uses stale ETag."
    - path: "tests/test_resetter.py"
      issue: "Line 471: test asserts buggy behavior (stale ETag) as correct"
  missing:
    - "Skip contacts_to_delete in step 6 (no point stripping notes before deletion) OR capture new ETag and propagate to step 7"
  debug_session: ".planning/debug/412-etag-stale-on-delete.md"
