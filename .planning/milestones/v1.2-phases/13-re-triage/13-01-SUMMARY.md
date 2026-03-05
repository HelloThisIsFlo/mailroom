---
phase: 13-re-triage
plan: 01
subsystem: api
tags: [carddav, jmap, vcard, etag, concurrency, contacts, triage-history]

# Dependency graph
requires:
  - phase: 12-label-scanning
    provides: "JMAP client with batch email operations and label management"
provides:
  - "CardDAV remove_from_group() with ETag retry pattern"
  - "JMAP query_emails_by_sender() for all-mailbox sender search"
  - "JMAP get_email_mailbox_ids() for per-email mailbox membership"
  - "Triage history note format with Mailroom header and chronological entries"
affects: [13-02-PLAN, 13-03-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Triage history notes: --- Mailroom --- header with chronological triage/re-triage entries"
    - "remove_from_group mirrors add_to_group ETag retry pattern"
    - "from-only JMAP filter for cross-mailbox sender queries"

key-files:
  created: []
  modified:
    - src/mailroom/clients/carddav.py
    - src/mailroom/clients/jmap.py
    - tests/test_carddav_client.py
    - tests/test_jmap_client.py

key-decisions:
  - "create_contact() now requires group_name as keyword-only arg for triage note"
  - "Triage history uses em-dash Mailroom header for programmatic detection"
  - "Old-format notes preserved as historical context above Mailroom section"
  - "get_email_mailbox_ids returns sets (not lists) for O(1) membership checks"

patterns-established:
  - "Triage history: --- Mailroom --- header + Triaged to / Re-triaged to entries"
  - "ETag-based optimistic concurrency for both add and remove group operations"

requirements-completed: [RTRI-01, RTRI-02, RTRI-04]

# Metrics
duration: 6min
completed: 2026-03-03
---

# Phase 13 Plan 01: Client Layer Methods Summary

**CardDAV remove_from_group with ETag retry, JMAP all-mailbox sender query and mailbox membership lookup, triage history note format**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-03T23:21:04Z
- **Completed:** 2026-03-03T23:27:16Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added `remove_from_group()` to CardDAV client mirroring `add_to_group()` ETag retry pattern, with idempotent removal and empty-member-list handling
- Added `query_emails_by_sender()` to JMAP client for cross-mailbox sender search with automatic pagination
- Added `get_email_mailbox_ids()` to JMAP client for per-email mailbox membership in BATCH_SIZE chunks
- Updated contact note format to triage history: `--- Mailroom ---` header with chronological `Triaged to` / `Re-triaged to` entries
- Old-format notes preserved as historical context with Mailroom section appended
- All 344 tests passing (7 new tests added)

## Task Commits

Each task was committed atomically (TDD: test -> feat):

1. **Task 1: CardDAV remove_from_group + triage history notes**
   - `d938956` (test: failing tests for remove_from_group and triage history)
   - `753dd8e` (feat: implement remove_from_group and triage history notes)
2. **Task 2: JMAP query_emails_by_sender + get_email_mailbox_ids**
   - `1c783ba` (test: failing tests for query_emails_by_sender and get_email_mailbox_ids)
   - `a44ff1a` (feat: implement query_emails_by_sender and get_email_mailbox_ids)

## Files Created/Modified
- `src/mailroom/clients/carddav.py` - Added remove_from_group(), updated create_contact() and upsert_contact() for triage history notes
- `src/mailroom/clients/jmap.py` - Added query_emails_by_sender() and get_email_mailbox_ids()
- `tests/test_carddav_client.py` - TestRemoveFromGroup class, updated note format expectations, note migration tests
- `tests/test_jmap_client.py` - TestQueryEmailsBySender and TestGetEmailMailboxIds classes

## Decisions Made
- `create_contact()` now requires `group_name` as a keyword-only argument (no default) to enforce triage note creation
- Triage history uses em-dash `--- Mailroom ---` header for programmatic detection (matches CONTEXT.md specification)
- Old-format notes are preserved above the Mailroom section (historical context, not discarded)
- `get_email_mailbox_ids()` returns `set[str]` values for O(1) mailbox membership checks
- Empty email ID list returns empty dict without API calls (short-circuit optimization)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed vCard NOTE escaping in test fixture**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** `_contact_vcard()` test helper wrote literal newlines into NOTE field, causing vobject parse errors when notes contained `\n` (new triage history format)
- **Fix:** Escape `\n` to `\\n` in the vCard NOTE field for proper vCard 3.0 encoding
- **Files modified:** tests/test_carddav_client.py
- **Verification:** All 49 CardDAV tests pass
- **Committed in:** 753dd8e (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary fix for test infrastructure to support multi-line notes. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All three client methods ready for screener workflow integration (Plan 02)
- Triage history note format established for upsert_contact callers
- Plan 02 can implement re-triage detection and group reassignment using these building blocks

---
*Phase: 13-re-triage*
*Completed: 2026-03-03*
