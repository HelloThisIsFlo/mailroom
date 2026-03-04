---
phase: 13-re-triage
verified: 2026-03-04T00:00:00Z
status: human_needed
score: 14/14 must-haves verified
re_verification: false
human_verification:
  - test: "Run python human-tests/test_17_retriage.py against live Fastmail with a pre-staged re-triage scenario"
    expected: "All 7 verification checks pass: contact moved to new group, note has Re-triaged entry, emails have new labels, old labels removed, Screener label removed, triage label removed"
    why_human: "test_17 runs against real Fastmail; automated checks cannot substitute for live account validation"
  - test: "Update REQUIREMENTS.md: mark RTRI-05 checkbox as [x] and traceability row as Complete"
    expected: "RTRI-05 reflects actual state (human test created, verification passed per 13-03-SUMMARY)"
    why_human: "REQUIREMENTS.md checkbox was not updated after Plan 03 completed -- documentation maintenance task"
---

# Phase 13: Re-triage Verification Report

**Phase Goal:** Re-triage -- detect already-grouped senders, reassign contact groups with chain diffing, reconcile email labels, log as structured event
**Verified:** 2026-03-04
**Status:** human_needed (all automated checks passed; one documentation inconsistency flagged)
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | remove_from_group() removes a contact from a CardDAV group with ETag-based optimistic concurrency | VERIFIED | `src/mailroom/clients/carddav.py:537` -- full retry loop with If-Match, 412 handling, RuntimeError after max_retries |
| 2  | remove_from_group() is idempotent -- returns cleanly if contact is already not a member | VERIFIED | `carddav.py:584` -- checks `if member_urn not in existing_urns: return current_etag` |
| 3  | query_emails_by_sender() returns all email IDs from a sender across all mailboxes (no inMailbox filter) | VERIFIED | `jmap.py:259` -- filter is `{"from": sender}` only, no inMailbox key |
| 4  | query_emails_by_sender() paginates automatically when total exceeds page size | VERIFIED | `jmap.py:283` -- `if len(ids) < limit: break` pagination loop (len-based, not total-based) |
| 5  | get_email_mailbox_ids() returns the mailboxIds dict for a batch of email IDs | VERIFIED | `jmap.py:332` -- BATCH_SIZE chunks, returns `{email_id: set(mailbox_ids)}` |
| 6  | create_contact() uses new triage history note format with Mailroom header | VERIFIED | `carddav.py:438-441` -- `"— Mailroom —\nTriaged to {group_name} on {date}"` |
| 7  | upsert_contact() uses new triage history note format, appending chronological entries | VERIFIED | `carddav.py:750-777` -- three branches: new format (append), old format (preserve + add header), empty (new section) |
| 8  | Already-grouped senders get re-triaged instead of receiving @MailroomError | VERIFIED | `screener.py:387-388` -- `_detect_retriage()` replaces `_check_already_grouped()`, no @MailroomError call in re-triage path |
| 9  | Re-triaged sender's emails re-filed by stripping ALL managed destination labels + Screener, then applying new additive labels | VERIFIED | `screener.py:547-618` -- `_reconcile_email_labels()` removes all managed IDs + screener_id, adds new chain dest IDs |
| 10 | Contact groups reassigned with safe add-first-then-remove order | VERIFIED | `screener.py:524-530` -- `_reassign_contact_groups()` adds `new_groups - old_groups` FIRST, then removes `old_groups - new_groups` |
| 11 | Same-group re-triage runs full label reconciliation (self-healing) | VERIFIED | `screener.py:422-425` -- re-triage branch always calls `_reconcile_email_labels()` regardless of same_group |
| 12 | Re-triage is logged as group_reassigned structured event with old_group, new_group, same_group fields | VERIFIED | `screener.py:437-445` -- `log.info("group_reassigned", old_group=..., new_group=..., same_group=..., emails_reconciled=...)` |
| 13 | Inbox is NEVER removed during re-triage; Inbox is added ONLY to emails currently in Screener when add_to_inbox is true | VERIFIED | `screener.py:578-591` -- Inbox explicitly excluded from removal set (`if managed_id != inbox_id`); Inbox added only when `add_to_inbox and screener_id in current_mailboxes` |
| 14 | test_17_retriage.py validates the full re-triage workflow end-to-end against live Fastmail | VERIFIED (artifact) | File exists at 395 lines, syntax-valid, calls `workflow.poll()` at line 260; human verification confirmed per 13-03-SUMMARY (all 7 checks passed against live Fastmail) |

**Score:** 14/14 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/mailroom/clients/carddav.py` | remove_from_group() method, updated create_contact/upsert_contact NOTE format | VERIFIED | `def remove_from_group` at line 537, triage history notes at lines 438-441 and 750-777 |
| `src/mailroom/clients/jmap.py` | query_emails_by_sender() and get_email_mailbox_ids() methods | VERIFIED | `def query_emails_by_sender` at line 241, `def get_email_mailbox_ids` at line 332 |
| `tests/test_carddav_client.py` | Tests for remove_from_group and triage history notes | VERIFIED | `TestRemoveFromGroup` class at line 820 |
| `tests/test_jmap_client.py` | Tests for query_emails_by_sender and get_email_mailbox_ids | VERIFIED | `TestQueryEmailsBySender` at line 1177, `TestGetEmailMailboxIds` at line 1336 |
| `src/mailroom/workflows/screener.py` | Re-triage detection and execution in _process_sender | VERIFIED | `group_reassigned` at line 440, `_detect_retriage` at line 479, `_reassign_contact_groups` at line 505, `_reconcile_email_labels` at line 532 |
| `tests/test_screener_workflow.py` | Re-triage unit tests replacing already-grouped error tests | VERIFIED | `TestRetriageDifferentGroup` (761), `TestRetriageSameGroup` (841), `TestRetriageNewSender` (898), `TestRetriageGroupChainDiff` (1909), `TestRetriageAddBeforeRemove` (1967), `TestRetriageLabelReconciliation` (2007), `TestRetriageInboxScreenerOnly` (2072), `TestRetriageStructuredLogging` (2119), `TestRetriageInitialTriageUnchanged` (2176) |
| `human-tests/test_17_retriage.py` | End-to-end re-triage human integration test | VERIFIED | 395 lines, syntax-valid, calls poll(), covers all 7 post-conditions |
| `human-tests/test_9_already_grouped.py` | Early exit redirect to test_17 | VERIFIED | Early exit before imports, prints redirect to test_17 at line 16 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/mailroom/clients/carddav.py` | vobject X-ADDRESSBOOKSERVER-MEMBER manipulation | remove_from_group mirrors add_to_group pattern | WIRED | Lines 580-596: fetch, check, filter, del or assign, PUT with If-Match |
| `src/mailroom/clients/jmap.py` | JMAP Email/query without inMailbox | query_emails_by_sender with from-only filter | WIRED | Line 259: `email_filter: dict = {"from": sender}` -- no inMailbox key present |
| `src/mailroom/workflows/screener.py` | carddav.remove_from_group() | _process_sender re-triage branch | WIRED | `screener.py:10` imports `get_parent_chain`; line 530: `self._carddav.remove_from_group(group, contact_uid)` |
| `src/mailroom/workflows/screener.py` | jmap.query_emails_by_sender() | _process_sender re-triage reconciliation | WIRED | Line 558: `self._jmap.query_emails_by_sender(sender)` inside `_reconcile_email_labels` |
| `src/mailroom/workflows/screener.py` | jmap.get_email_mailbox_ids() | Screener presence check for add_to_inbox | WIRED | Line 563: `self._jmap.get_email_mailbox_ids(all_email_ids)` |
| `src/mailroom/workflows/screener.py` | config.get_parent_chain() | chain diff for group reassignment | WIRED | Lines 519-520 in `_reassign_contact_groups`: old_chain and new_chain computed via `get_parent_chain` |
| `human-tests/test_17_retriage.py` | ScreenerWorkflow.poll() | imports and runs poll against live Fastmail | WIRED | Line 260: `processed = workflow.poll()` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| RTRI-01 | 13-01, 13-02 | Applying a triage label to an already-grouped sender moves them to the new contact group | SATISFIED | `_detect_retriage()` + `_reassign_contact_groups()` in screener.py; @MailroomError path removed |
| RTRI-02 | 13-01, 13-02 | Re-triaged sender's emails re-filed by fetching ALL emails across all mailboxes | SATISFIED | `_reconcile_email_labels()` calls `query_emails_by_sender()` (no mailbox filter), applies new additive chain labels |
| RTRI-03 | 13-02 | Re-triage logged as group_reassigned structured event | SATISFIED | `screener.py:437-445` -- `log.info("group_reassigned", ...)` with all required fields |
| RTRI-04 | 13-01 | Contact note captures triage history | SATISFIED (note: wording mismatch) | Code uses "Triaged to / Re-triaged to" format; REQUIREMENTS.md describes "Added to / Moved from" -- intent identical, wording diverged. Functional requirement met. |
| RTRI-05 | 13-03 | Human integration test validates re-triage workflow end-to-end | SATISFIED (artifact present; REQUIREMENTS.md checkbox not updated) | test_17_retriage.py exists (395 lines), human verification passed all 7 checks per 13-03-SUMMARY; checkbox `[ ]` in REQUIREMENTS.md still shows Pending -- documentation only |
| RTRI-06 | 13-02 | add_to_inbox only adds Inbox to emails in Screener at triage time | SATISFIED | `screener.py:589-591`: Inbox added only when `add_to_inbox and screener_id in current_mailboxes`; Inbox explicitly excluded from removal loop at line 580 |

### Anti-Patterns Found

No anti-patterns detected in modified source files (carddav.py, jmap.py, screener.py, test_17_retriage.py, test_9_already_grouped.py). No TODO/FIXME/placeholder comments. No stub return patterns. No empty handlers.

### Human Verification Required

#### 1. Live re-triage end-to-end test

**Test:** Set up a sender in Fastmail with a triage label pointing to a different group than their current contact group, then run `python human-tests/test_17_retriage.py`

**Expected:** All 7 post-condition checks pass: contact is now in the new group, contact note contains "Re-triaged to" entry, emails have new destination labels, old destination labels removed, Screener label removed from any Screener emails, triage label removed

**Why human:** test_17 connects to the real Fastmail account via JMAP + CardDAV. Automated unit tests mock all external calls. The 13-03-SUMMARY reports this was verified on 2026-03-03 with 260 emails reconciled (contact moved from Bank to Feed group), but the canonical record is that human verification was completed -- this entry documents the re-run requirement for formal phase sign-off.

#### 2. Update REQUIREMENTS.md RTRI-05 status

**Test:** Update `.planning/REQUIREMENTS.md` line 41 from `- [ ] **RTRI-05**` to `- [x] **RTRI-05**` and line 99 from `| RTRI-05 | Phase 13 | Pending |` to `| RTRI-05 | Phase 13 | Complete |`

**Expected:** REQUIREMENTS.md accurately reflects that the human integration test exists and verification passed

**Why human:** This is a documentation maintenance decision. The artifact exists and verification passed per the summary -- but the checkbox was not updated during Plan 03 execution. A human should confirm the status and apply the update.

### Gaps Summary

No functional gaps. All 14 must-have truths are verified against the actual codebase. All 9 commits referenced in summaries exist in git log. The full test suite passes with 359 tests.

Two minor items need human attention:

1. **RTRI-05 documentation lag:** REQUIREMENTS.md still shows RTRI-05 as Pending/unchecked, but test_17_retriage.py exists (395 lines, syntax-valid) and 13-03-SUMMARY documents successful human verification on 2026-03-03 (7/7 checks passed against live Fastmail). The artifact satisfies the requirement; only the REQUIREMENTS.md tracking needs updating.

2. **RTRI-04 wording mismatch:** REQUIREMENTS.md describes the note format as `"Added to [group] on [date]"` and `"Moved from [old] to [new] on [date]"`, but the implementation uses `"Triaged to {group_name} on {date}"` and `"Re-triaged to {group_name} on {date}"`. This is a documentation vs. implementation divergence -- not a bug, the intent is identical. The CONTEXT.md and PLAN both specified the implemented wording.

---

_Verified: 2026-03-04_
_Verifier: Claude (gsd-verifier)_
