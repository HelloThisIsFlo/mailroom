---
phase: 02-carddav-client-validation-gate
plan: 01
subsystem: api
tags: [carddav, httpx, vobject, vcard, webdav, xml, fastmail]

# Dependency graph
requires:
  - phase: 01-foundation-and-jmap-client
    provides: httpx dependency, config pattern (MailroomSettings), client class structure (JMAPClient)
provides:
  - CardDAVClient class with connect() and validate_groups()
  - PROPFIND-based addressbook discovery (3-step chain)
  - Apple-style KIND:group vCard parsing with vobject
  - Config fields: carddav_username, label_mailroom_error, contact_groups property
affects: [02-02, 02-03, 03-triage-pipeline]

# Tech tracking
tech-stack:
  added: [vobject]
  patterns: [PROPFIND discovery chain, 207 Multi-Status XML parsing, Apple-style group vCard detection]

key-files:
  created:
    - src/mailroom/clients/carddav.py
    - tests/test_carddav_client.py
  modified:
    - src/mailroom/core/config.py
    - pyproject.toml

key-decisions:
  - "REPORT addressbook-query with no filter for fetching all vCards (single round-trip vs multiple GETs)"
  - "card.contents.get('x-addressbookserver-kind') for vobject property access (reliable dict access over attribute access)"
  - "Full absolute URLs stored in _addressbook_url (hostname + path) for simpler downstream usage"

patterns-established:
  - "CardDAVClient follows JMAPClient pattern: constructor, connect(), guard, operations"
  - "XML namespace constants at module level using Clark notation: DAV = '{DAV:}'"
  - "_parse_multistatus() reusable for all 207 responses (PROPFIND and REPORT)"

requirements-completed: [CDAV-01]

# Metrics
duration: 3min
completed: 2026-02-24
---

# Phase 2 Plan 1: CardDAV Client Foundation Summary

**CardDAV client with Basic auth, 3-step PROPFIND addressbook discovery, and Apple-style group validation using vobject**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-24T02:32:56Z
- **Completed:** 2026-02-24T02:36:32Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- CardDAVClient authenticates via httpx.BasicAuth and discovers the default addressbook through a 3-step PROPFIND chain (principal -> home -> addressbook)
- Group validation fetches all vCards via REPORT addressbook-query, filters by X-ADDRESSBOOKSERVER-KIND:group, and matches FN against required group names
- Config updated with carddav_username, label_mailroom_error, and contact_groups property (backward-compatible empty defaults)
- 7 unit tests covering connection discovery, auth failure, connection guard, and group validation (all groups found, missing group error, non-group filtering)

## Task Commits

Each task was committed atomically:

1. **Task 1: Config update and CardDAV client scaffold with connection tests** - `e1bbd80` (feat)
2. **Task 2: Group validation with TDD** - `ef6271d` (test)

## Files Created/Modified
- `src/mailroom/clients/carddav.py` - CardDAVClient with connect(), validate_groups(), _parse_multistatus(), connection guard
- `tests/test_carddav_client.py` - 7 tests: 4 connection, 3 group validation (342 lines)
- `src/mailroom/core/config.py` - Added carddav_username, label_mailroom_error, contact_groups property
- `pyproject.toml` - Added vobject dependency
- `uv.lock` - Updated lockfile

## Decisions Made
- Used REPORT addressbook-query with no filter (single round-trip) instead of PROPFIND + individual GETs for fetching all vCards during group validation
- Used `card.contents.get("x-addressbookserver-kind")` for vobject property access -- dict-based access is more reliable than attribute access for X-properties
- Stored full absolute URL in `_addressbook_url` (e.g., `https://carddav.fastmail.com/dav/.../Default/`) rather than relative path, simplifying downstream usage

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed lint issues in test file**
- **Found during:** Task 2 (Group validation tests)
- **Issue:** Line length violations (E501) in assertion dict literals and unnecessary UTF-8 encoding argument (UP012)
- **Fix:** Reformatted dict assertions to multi-line and removed `.encode("utf-8")` argument
- **Files modified:** tests/test_carddav_client.py
- **Verification:** `uv run ruff check src/ tests/` passes
- **Committed in:** ef6271d (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug/lint)
**Impact on plan:** Minor formatting fix. No scope creep.

## Issues Encountered
- vobject installed as v0.9.9 (not 1.0.0 as research assumed) -- API is identical, no impact

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CardDAVClient foundation ready for Plan 02 (contact search/create/update operations)
- validate_groups() stores group info in `self._groups` for use by add_to_group() in Plan 02
- PROPFIND discovery proven in tests -- same pattern will work against live Fastmail in human tests

## Self-Check: PASSED

All files and commits verified:
- src/mailroom/clients/carddav.py: FOUND
- tests/test_carddav_client.py: FOUND
- src/mailroom/core/config.py: FOUND
- 02-01-SUMMARY.md: FOUND
- Commit e1bbd80: FOUND
- Commit ef6271d: FOUND

---
*Phase: 02-carddav-client-validation-gate*
*Completed: 2026-02-24*
