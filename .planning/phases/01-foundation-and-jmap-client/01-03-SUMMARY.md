---
phase: 01-foundation-and-jmap-client
plan: 03
subsystem: clients
tags: [jmap, httpx, fastmail, email-query, email-set, pagination, pytest-httpx, tdd]

# Dependency graph
requires:
  - "01-02: JMAPClient with connect(), call(), resolve_mailboxes() methods"
provides:
  - "JMAPClient.query_emails() with inMailbox filter, optional sender, auto-pagination"
  - "JMAPClient.get_email_senders() extracts sender addresses from Email/get response"
  - "JMAPClient.remove_label() removes single mailbox label via patch syntax"
  - "JMAPClient.batch_move_emails() batch-moves with chunking at 100, source removal + destination addition"
  - "14 new tests covering all email operations with mocked httpx responses"
affects: [03-triage-workflow, 04-main-loop]

# Tech tracking
tech-stack:
  added: []
  patterns: [jmap-email-query-pagination, jmap-patch-syntax-labels, batch-chunking-at-100, email-set-error-handling]

key-files:
  created: []
  modified:
    - src/mailroom/clients/jmap.py
    - tests/test_jmap_client.py

key-decisions:
  - "query_emails() combines JMAP-03 and JMAP-06 in a single method with optional sender parameter"
  - "Imbox/Inbox special case is caller responsibility -- batch_move_emails() is generic, caller passes inbox_id in add_mailbox_ids"
  - "Batch chunking at 100 emails per Email/set call (conservative under Fastmail's 500 minimum maxObjectsInSet)"
  - "No REFACTOR phase needed -- GREEN implementation was clean and well-documented"

patterns-established:
  - "Email operation pattern: build JMAP method call args, call via self.call(), extract data from responses[0][1]"
  - "Pagination pattern: while-loop checking len(all_ids) >= total, incrementing position offset"
  - "Error handling pattern: check notUpdated in Email/set response, raise RuntimeError with failed IDs and descriptions"
  - "Patch syntax pattern: mailboxIds/{id}: null (remove) or true (add) for safe label operations"

requirements-completed: [JMAP-03, JMAP-04, JMAP-05, JMAP-06, JMAP-07, JMAP-08]

# Metrics
duration: 3min
completed: 2026-02-24
---

# Phase 1 Plan 3: JMAP Email Query, Sender Extraction, and Batch Move Summary

**Email query with auto-pagination, sender extraction via Email/get, label removal and batch move via patch syntax -- 14 new tests via TDD (RED-GREEN)**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-24T01:09:22Z
- **Completed:** 2026-02-24T01:12:08Z
- **Tasks:** 2 (TDD RED + GREEN; REFACTOR not needed)
- **Files modified:** 2

## Accomplishments
- query_emails() queries email IDs in a mailbox with optional sender filter and automatic pagination via position offset
- get_email_senders() extracts sender email addresses from Email/get response, mapping email_id to sender address
- remove_label() safely removes a single mailbox label using JMAP patch syntax (mailboxIds/{id}: null)
- batch_move_emails() batch-moves emails in chunks of 100, removing source label and adding destination labels in a single Email/set call
- Imbox special case handled generically: caller passes inbox_id in add_mailbox_ids list
- 14 new tests (5 query, 3 sender, 2 label, 4 batch) -- 37 total passing across project

## Task Commits

TDD RED-GREEN cycle:

1. **RED: Failing tests for email query, sender extraction, and batch move** - `658f002` (test)
2. **GREEN: Implement all email operations passing 14 new tests** - `8bae25c` (feat)

No REFACTOR commit needed -- implementation was clean from the start.

## Files Created/Modified
- `src/mailroom/clients/jmap.py` - Extended JMAPClient with query_emails(), get_email_senders(), remove_label(), batch_move_emails() methods and BATCH_SIZE constant (322 lines, was 141)
- `tests/test_jmap_client.py` - 14 new tests across 4 test classes (TestQueryEmails, TestGetEmailSenders, TestRemoveLabel, TestBatchMoveEmails) using pytest-httpx mocks (872 lines, was 281)

## Decisions Made
- **Combined query method:** query_emails() serves both JMAP-03 (query by mailbox) and JMAP-06 (query by mailbox + sender) via optional `sender` parameter. No need for a separate method since the only difference is adding `from` to the filter.
- **Generic batch move:** batch_move_emails() takes `add_mailbox_ids: list[str]` rather than having a separate Imbox method. The caller passes `[imbox_id, inbox_id]` for Imbox destinations and `[feed_id]` for Feed destinations. This keeps the JMAP client layer generic.
- **Chunk size 100:** Conservative batching at 100 emails per Email/set call. JMAP spec minimum maxObjectsInSet is 500, but 100 is safer and leaves room for Fastmail-specific limits.
- **No REFACTOR phase:** The GREEN implementation was already clean, well-documented, and followed the established patterns from Plan 02.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused `failed_ids` variable in remove_label()**
- **Found during:** Task 2 (GREEN implementation)
- **Issue:** ruff flagged `failed_ids = list(not_updated.keys())` as assigned but never used (F841)
- **Fix:** Removed the unused assignment; error messages already include the IDs via the `errors` list comprehension
- **Files modified:** src/mailroom/clients/jmap.py
- **Verification:** ruff check passes clean
- **Committed in:** 8bae25c (part of GREEN commit)

**2. [Rule 1 - Bug] Fixed module docstring line length**
- **Found during:** Task 2 (GREEN implementation)
- **Issue:** ruff flagged module docstring exceeding 100-char line limit (E501)
- **Fix:** Shortened docstring from 105 to 75 characters
- **Files modified:** src/mailroom/clients/jmap.py
- **Verification:** ruff check passes clean
- **Committed in:** 8bae25c (part of GREEN commit)

---

**Total deviations:** 2 auto-fixed (2 bugs caught by linter)
**Impact on plan:** Both trivial lint fixes, no scope creep.

## Issues Encountered
None -- all tests passed on first GREEN implementation.

## User Setup Required
None -- no external service configuration required. All tests use mocked HTTP responses.

## Next Phase Readiness
- JMAPClient is now complete with all email operations needed for the triage workflow
- Phase 1 is fully complete (3/3 plans done): config, logging, session discovery, mailbox resolution, email query, sender extraction, label removal, batch move
- Ready for Phase 2 (CardDAV contact group verification) which will add a separate client
- Ready for Phase 3 (triage workflow) which will compose JMAPClient methods into the sweep/relabel/remove pipeline
- 37 total tests passing across the project (10 config/logging + 27 JMAP client)

## Self-Check: PASSED

All 2 files verified present. Both commit hashes verified in git log. Line counts: jmap.py=322 (>=150), test_jmap_client.py=872 (>=150).
