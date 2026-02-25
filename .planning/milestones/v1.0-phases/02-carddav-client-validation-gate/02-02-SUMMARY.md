---
phase: 02-carddav-client-validation-gate
plan: 02
subsystem: api
tags: [carddav, httpx, vobject, vcard, webdav, xml, etag, contacts, groups]

# Dependency graph
requires:
  - phase: 02-carddav-client-validation-gate
    provides: CardDAVClient with connect(), validate_groups(), _parse_multistatus()
provides:
  - search_by_email() via REPORT addressbook-query with case-insensitive email filter
  - create_contact() producing valid vCard 3.0 with If-None-Match safety
  - add_to_group() with X-ADDRESSBOOKSERVER-MEMBER and If-Match/412 retry
  - upsert_contact() orchestrating search-create/merge-group flow
affects: [02-03, 03-triage-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns: [REPORT addressbook-query with prop-filter, ElementTree XML construction for search, vobject vCard serialization, ETag retry loop, merge-cautious update]

key-files:
  created: []
  modified:
    - src/mailroom/clients/carddav.py
    - tests/test_carddav_client.py

key-decisions:
  - "ElementTree for REPORT XML body construction (proper escaping of email special chars like &, <)"
  - "First-match strategy for duplicate contacts during upsert (deterministic, uses first search result)"
  - "Merge-cautious: only fill empty fields, never overwrite existing FN/N/NOTE data"
  - "Skip PUT in add_to_group when contact already a member (idempotent)"

patterns-established:
  - "ETag retry loop pattern: GET -> modify -> PUT with If-Match -> retry on 412"
  - "Merge-cautious update: check each field before writing, track 'changed' flag for conditional PUT"
  - "upsert_contact as orchestrator: search -> create/merge -> add_to_group"

requirements-completed: [CDAV-02, CDAV-03, CDAV-04, CDAV-05]

# Metrics
duration: 4min
completed: 2026-02-24
---

# Phase 2 Plan 2: Contact Operations Summary

**CardDAV contact search via REPORT addressbook-query, vCard 3.0 creation with vobject, group membership with ETag-safe retry, and merge-cautious upsert orchestration**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-24T02:40:02Z
- **Completed:** 2026-02-24T02:44:22Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- search_by_email sends REPORT addressbook-query with case-insensitive EMAIL prop-filter using ElementTree-constructed XML (proper escaping)
- create_contact builds valid vCard 3.0 (FN, N, EMAIL, NOTE, UID) via vobject with If-None-Match: * safety and email prefix fallback
- add_to_group modifies group vCard with X-ADDRESSBOOKSERVER-MEMBER, uses If-Match ETag for concurrency safety, retries on 412 up to 3 times, and skips PUT when contact is already a member
- upsert_contact orchestrates the full flow: search -> create or merge-cautious update -> add to group, preventing duplicates by searching before creating
- 18 new unit tests (5 search + 4 create + 5 group + 4 upsert), 25 total CardDAV tests, 62 total project tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Search by email and create contact with TDD** - `68eb3ed` (feat)
2. **Task 2: Group membership, merge-cautious update, and upsert orchestration with TDD** - `7de9aa8` (feat)

## Files Created/Modified
- `src/mailroom/clients/carddav.py` - Added search_by_email, create_contact, add_to_group, upsert_contact methods (527 lines total)
- `tests/test_carddav_client.py` - Added 18 new tests across 4 test classes (986 lines total)

## Decisions Made
- Used ElementTree (not f-strings) for REPORT XML body construction to properly escape email addresses with special XML characters
- First-match strategy when multiple contacts match an email during upsert (deterministic, avoids complexity of merge-across-contacts)
- Merge-cautious update only fills empty fields (FN, N, NOTE) and adds missing emails; never overwrites existing data
- add_to_group is idempotent: skips PUT when contact UID is already in the group's MEMBER list

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed lint issues in module docstrings and imports**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** E501 line-too-long in module docstrings (>100 chars), F401 unused xml_escape import, I001 unsorted imports
- **Fix:** Shortened docstrings, removed unused import, fixed import ordering
- **Files modified:** src/mailroom/clients/carddav.py, tests/test_carddav_client.py
- **Verification:** `uv run ruff check src/ tests/` passes
- **Committed in:** 68eb3ed (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 lint)
**Impact on plan:** Minor formatting fix. No scope creep.

## Issues Encountered
None - implementation followed plan specifications exactly.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CardDAVClient is feature-complete for Phase 3 triage pipeline usage
- All contact operations tested with mocked httpx responses
- Plan 03 (human validation tests) will verify against live Fastmail
- Key methods available: connect(), validate_groups(), search_by_email(), create_contact(), add_to_group(), upsert_contact()

## Self-Check: PASSED

All files and commits verified:
- src/mailroom/clients/carddav.py: FOUND
- tests/test_carddav_client.py: FOUND
- 02-02-SUMMARY.md: FOUND
- Commit 68eb3ed: FOUND
- Commit 7de9aa8: FOUND

---
*Phase: 02-carddav-client-validation-gate*
*Completed: 2026-02-24*
