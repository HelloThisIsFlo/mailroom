---
status: complete
phase: 13-re-triage
source: [13-01-SUMMARY.md, 13-02-SUMMARY.md, 13-03-SUMMARY.md]
started: 2026-03-04T00:00:00Z
updated: 2026-03-04T00:05:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Re-triage sender to different category
expected: Move a sender's email into a different triage label (e.g., from Bank's triage label to Feed's). Run a poll. The sender's contact should move from the old contact group to the new one. The sender should NOT get an @MailroomError label — re-triage replaces the old already-grouped error path entirely.
result: pass

### 2. Email label reconciliation after re-triage
expected: After re-triaging a sender, their existing emails should have old destination labels stripped and new destination labels applied. For example, if moved from Bank to Feed, emails lose the Bank mailbox label and gain the Feed mailbox label. Inbox label is never removed.
result: pass

### 3. Triage history in contact notes
expected: After re-triage, the contact's note field should contain a "--- Mailroom ---" section with a chronological "Re-triaged to [new category]" entry below any existing "Triaged to [old category]" entry.
result: pass

### 4. Same-group re-triage (self-healing)
expected: Re-triage a sender to the same category they're already in. The system should run full reconciliation (fixing any label drift) without errors, even though the group doesn't change. No @MailroomError.
result: pass

### 5. Human test_17 runs end-to-end
expected: Run `python human-tests/test_17_retriage.py`. The test should execute against live Fastmail, performing a re-triage and verifying group move, email label reconciliation, triage label removal, and contact note history. All checks pass.
result: skipped
reason: Already verified re-triage end-to-end via tests 1-4 against live Fastmail in K8s. Running test_17 would require tearing down the deployment.

### 6. Deprecated test_9 redirects to test_17
expected: Run `python human-tests/test_9_already_grouped.py`. Instead of executing, it should print a message redirecting to test_17 and exit cleanly (exit code 0).
result: pass

## Summary

total: 6
passed: 4
issues: 0
pending: 0
skipped: 1

## Gaps

[none]
