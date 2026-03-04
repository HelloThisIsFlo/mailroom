---
status: resolved
trigger: "When triaging an email from the Screener mailbox to a category, the system does NOT sweep all existing emails from that sender into the new category. It only processes emails in the Screener. However, triaging again (same group, second time) fixes everything."
created: 2026-03-04T00:00:00Z
updated: 2026-03-04T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED - Fix applied and verified
test: All 362 tests pass including new regression test
expecting: N/A - awaiting human verification
next_action: None - resolved

## Symptoms

expected: When you triage an email to a category from the Screener (or anywhere), it should sweep ALL existing emails from that sender into the new category — regardless of where the triage was initiated.
actual: When triaging from the Screener, it only processes emails in the Screener — it doesn't sweep older emails from other mailboxes. But triaging again (same group, second time) fixes it and sweeps everything correctly.
errors: No error messages reported — the operation succeeds, it just doesn't sweep broadly enough on first triage from Screener.
reproduction: 1) Have emails from a sender in both Screener and other mailboxes. 2) Triage the sender from the Screener to a category. 3) Observe: only Screener emails get processed. 4) Triage again (same category) — now all emails get swept correctly.
started: Since retriage/sweep feature was implemented

## Eliminated

## Evidence

- timestamp: 2026-03-04T00:01:00Z
  checked: _process_sender method in screener.py, lines 422-434
  found: |
    Initial triage (else branch) calls:
      self._jmap.query_emails(screener_id, sender=sender)
    This uses inMailbox filter scoped to Screener ONLY.

    Retriage (if is_retriage branch) calls:
      self._reconcile_email_labels() which internally calls:
      self._jmap.query_emails_by_sender(sender)
    This searches across ALL mailboxes (no inMailbox filter).
  implication: First triage from Screener only finds/sweeps emails IN the Screener. Second triage triggers retriage path which sweeps ALL mailboxes.

- timestamp: 2026-03-04T00:02:00Z
  checked: _detect_retriage method, lines 479-503
  found: |
    is_retriage = contact_uid is not None and old_group is not None
    After first triage, the contact is created AND added to a group.
    So second triage correctly detects as retriage and runs the full sweep path.
  implication: Confirms the user's observation - second triage works because is_retriage=True triggers the all-mailbox code path.

- timestamp: 2026-03-04T00:03:00Z
  checked: query_emails vs query_emails_by_sender in jmap.py
  found: |
    query_emails(mailbox_id, sender) uses filter: {"inMailbox": mailbox_id, "from": sender}
    query_emails_by_sender(sender) uses filter: {"from": sender} only
  implication: Confirms the query scope difference is the mechanism behind the bug.

- timestamp: 2026-03-04T00:04:00Z
  checked: Existing tests in test_screener_workflow.py
  found: |
    test_initial_triage_uses_screener_sweep (line 2197) ASSERTS that initial triage
    uses query_emails (Screener-only) and NOT query_emails_by_sender.
    test_sweep_queries_screener (line 511) similarly asserts Screener-only scope.
    These tests encode the WRONG behavior as correct.
  implication: Tests need updating alongside the fix. The tests were written to match the (incorrect) implementation, not the desired behavior.

## Resolution

root_cause: |
  In _process_sender (screener.py line 426-434), the initial triage path only sweeps
  emails from the Screener mailbox using query_emails(screener_id, sender=sender).
  It should sweep ALL emails from that sender across all mailboxes, similar to what
  _reconcile_email_labels does for retriage using query_emails_by_sender(sender).

  The retriage path works correctly because _reconcile_email_labels calls
  query_emails_by_sender(sender) which searches all mailboxes.

fix: |
  Unified initial triage and retriage to both use _reconcile_email_labels().
  Removed the separate Screener-only sweep path (query_emails + batch_move_emails)
  from the initial triage branch in _process_sender.

  Now both paths call _reconcile_email_labels() which:
  1. Queries ALL emails from sender across all mailboxes (query_emails_by_sender)
  2. Gets per-email mailbox membership
  3. Strips all managed destination labels + Screener from every email
  4. Applies new destination labels (child + parent chain)
  5. Handles add_to_inbox only for Screener emails

verification: |
  - All 362 tests pass (138 screener workflow tests)
  - 16 tests updated to reflect new reconciliation-based sweep
  - 3 new tests added (TestInitialTriageSweepsAllMailboxes) verifying the fix
  - New regression test confirms emails outside Screener get new labels applied

files_changed:
  - src/mailroom/workflows/screener.py
  - tests/test_screener_workflow.py
