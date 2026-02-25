---
status: complete
phase: 03-triage-pipeline
source: [03-01-SUMMARY.md, 03-02-SUMMARY.md, 03-03-SUMMARY.md]
started: 2026-02-24T16:00:00Z
updated: 2026-02-24T16:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Full Test Suite Passes
expected: Running `pytest` from the project root completes with all 137 tests passing (0 failures, 0 errors).
result: pass

### 2. Sender Display Name Extracted from JMAP From Header
expected: get_email_senders() returns both the email address and the display name from the JMAP From header. Empty/whitespace names are normalized to None.
human-test: `python human-tests/test_2_query.py`
result: pass
note: Confirmed via human test 2

### 3. Display Name Propagates Through Pipeline to Contact Creation
expected: When poll() processes a sender, the display name flows from _collect_triaged() through to _process_sender() and is passed to upsert_contact(). Contacts are created with the sender's real name, not the email prefix.
human-test: `python human-tests/test_7_screener_poll.py`
result: pass
note: Confirmed via human test 7 — contact created with correct display name

### 4. Poll Cycle Collects Triaged Emails Across All 4 Labels
expected: ScreenerWorkflow.poll() queries for emails tagged with each of the 4 triage labels (Imbox, Feed, Paper Trail, Jail), groups them by sender address, and returns results for per-sender processing.
human-test: `python human-tests/test_7_screener_poll.py`
result: pass
note: Confirmed via human test 7

### 5. All 4 Destination Types Route Correctly
expected: Imbox-labeled emails move to Inbox mailbox, Feed-labeled to Feed mailbox, Paper Trail-labeled to Paper Trail mailbox, Jail-labeled to Jail mailbox. Destination resolution uses config's destination_mailbox mapping.
human-test: `python human-tests/test_7_screener_poll.py`
result: pass
note: Confirmed via human test 7

### 6. Per-Sender Processing Follows Strict Step Order
expected: _process_sender executes in strict order: (1) check if already grouped, (2) upsert contact to CardDAV, (3) sweep/move emails to destination mailbox, (4) remove triage label. Steps never execute out of order.
human-test: `python human-tests/test_7_screener_poll.py`
result: pass
note: Confirmed via human test 7 (structlog output shows step order)

### 7. Conflicting Triage Labels Detected and Error-Labeled
expected: When the same sender has emails with different triage labels (e.g., some tagged Imbox, others tagged Feed), the workflow detects the conflict and applies @MailroomError label additively to all affected emails without removing the original labels.
human-test: `python human-tests/test_8_conflict_detection.py`
result: pass

### 8. Already-Grouped Sender in Different Group Gets Error Label
expected: If a sender's contact already exists in a different group (e.g., contact is in Feed group but new email is tagged Imbox), @MailroomError is applied and processing stops. If already in the same group, processing proceeds normally (idempotent).
human-test: `python human-tests/test_9_already_grouped.py`
result: pass

### 9. Transient Failures Are Retry-Safe
expected: If any step in _process_sender fails (JMAP or CardDAV transient error), the triage label stays on the email so it gets retried on the next poll cycle. The poll cycle itself does not crash.
human-test: `python human-tests/test_10_retry_safety.py`
result: pass

## Summary

total: 9
passed: 9
issues: 0
pending: 0
skipped: 0

## Gaps

[none]
