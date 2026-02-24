---
phase: 01-foundation-and-jmap-client
plan: 02
subsystem: clients
tags: [jmap, httpx, fastmail, pytest-httpx, tdd]

# Dependency graph
requires:
  - "01-01: Python project scaffold with src/ layout, httpx + pytest-httpx dependencies"
provides:
  - "JMAPClient class with connect(), call(), and resolve_mailboxes() methods"
  - "Session discovery: Bearer token auth, account_id and api_url extraction"
  - "Mailbox resolution: name-to-ID map with role-based Inbox lookup and top-level preference"
  - "13 tests covering session discovery, mailbox resolution, and error handling"
affects: [01-03, 03-triage-workflow, 04-main-loop]

# Tech tracking
tech-stack:
  added: []
  patterns: [thin-jmap-client-over-httpx, role-based-inbox-lookup, top-level-mailbox-preference, pytest-httpx-mocking]

key-files:
  created:
    - src/mailroom/clients/jmap.py
    - tests/test_jmap_client.py
  modified: []

key-decisions:
  - "Inbox resolved by role='inbox' (not name) to avoid parent/child name collisions per JMAP spec"
  - "Custom mailboxes prefer top-level (parentId=None) when duplicate names exist at different hierarchy levels"
  - "RuntimeError raised for pre-connect access (account_id, call) with descriptive messages"
  - "JMAP capabilities include both core and mail URNs in every request"

patterns-established:
  - "JMAP client pattern: connect() for session discovery, call() for method execution, resolve_mailboxes() for startup validation"
  - "Test pattern: pytest-httpx with add_response for mocked HTTP, add_exception for error paths"
  - "Connection guard pattern: RuntimeError with 'not connected' message before connect() is called"

requirements-completed: [JMAP-01, JMAP-02]

# Metrics
duration: 2min
completed: 2026-02-24
---

# Phase 1 Plan 2: JMAP Session Discovery and Mailbox Resolution Summary

**Thin JMAP client over httpx with Bearer auth session discovery, role-based Inbox resolution, and top-level mailbox preference -- 13 tests via TDD (RED-GREEN)**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-24T01:04:59Z
- **Completed:** 2026-02-24T01:07:08Z
- **Tasks:** 2 (TDD RED + GREEN; REFACTOR not needed)
- **Files modified:** 2

## Accomplishments
- JMAPClient.connect() authenticates with Fastmail using Bearer token, extracts account_id and api_url from session response
- JMAPClient.resolve_mailboxes() fetches all mailboxes via Mailbox/get, builds name-to-ID map with role-based Inbox lookup
- Missing mailboxes raise ValueError listing all missing names (fail-fast for startup validation)
- 13 tests covering: connect success/failure/network error, Bearer auth header, Inbox by role, duplicate name preference, missing mailboxes, call() lifecycle

## Task Commits

TDD RED-GREEN cycle:

1. **RED: Failing tests for session discovery and mailbox resolution** - `1965928` (test)
2. **GREEN: Implement JMAPClient passing all 13 tests** - `bf74b88` (feat)

No REFACTOR commit needed -- implementation was clean from the start.

## Files Created/Modified
- `src/mailroom/clients/jmap.py` - JMAPClient class: connect() session discovery, call() JMAP method execution, resolve_mailboxes() name-to-ID mapping (141 lines)
- `tests/test_jmap_client.py` - 13 tests across 3 test classes (TestConnect, TestResolveMailboxes, TestCall) using pytest-httpx mocks (281 lines)

## Decisions Made
- **Inbox by role, not name:** The `resolve_mailboxes()` method resolves "Inbox" by matching `role="inbox"` rather than `name="Inbox"`. This avoids a known JMAP pitfall where child mailboxes can share the same name as their parent (JMAP names are only unique within a parent, not globally).
- **Top-level preference for custom mailboxes:** When duplicate custom mailbox names exist at different hierarchy levels, the top-level one (parentId=None) is preferred. This handles edge cases where users might have nested folders with the same name.
- **RuntimeError for pre-connect access:** Both `account_id` property and `call()` method raise RuntimeError with a "not connected" message if accessed before `connect()`. This provides clear diagnostics vs. silent None failures.
- **No REFACTOR phase:** The GREEN implementation was already clean, well-documented, and concise at 141 lines. No extraction or reorganization needed.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None - all tests passed on first GREEN implementation.

## User Setup Required
None - no external service configuration required. All tests use mocked HTTP responses.

## Next Phase Readiness
- JMAPClient is ready for Plan 03 (JMAP email query, sender extraction, batch move operations)
- The `call()` method provides the foundation for all remaining JMAP methods (Email/query, Email/get, Email/set)
- `resolve_mailboxes()` will be used at startup to build the mailbox ID map needed by the triage workflow
- 23 total tests passing across the project (10 from Plan 01 + 13 from Plan 02)

## Self-Check: PASSED

All 2 files verified present. Both commit hashes verified in git log. Line counts: jmap.py=141 (>=60), test_jmap_client.py=281 (>=80).

---
*Phase: 01-foundation-and-jmap-client*
*Completed: 2026-02-24*
