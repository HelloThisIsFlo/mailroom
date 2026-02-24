---
phase: 02-carddav-client-validation-gate
plan: 03
subsystem: testing
tags: [carddav, human-tests, fastmail, validation-gate, contacts, groups, etag]

# Dependency graph
requires:
  - phase: 02-carddav-client-validation-gate
    provides: CardDAVClient with connect(), validate_groups(), search_by_email(), create_contact(), add_to_group(), upsert_contact()
provides:
  - Human test scripts validating CardDAV auth, contact ops, and group membership against live Fastmail
  - Live Fastmail validation confirming Phase 2 success criteria
  - .env.example with CardDAV credential placeholders
affects: [03-triage-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns: [human test scripts with dotenv + PASS/FAIL pattern, interactive ETag conflict testing]

key-files:
  created:
    - human-tests/test_4_carddav_auth.py
    - human-tests/test_5_carddav_contacts.py
    - human-tests/test_6_carddav_groups.py
  modified:
    - human-tests/.env.example
    - src/mailroom/clients/carddav.py

key-decisions:
  - "ETag conflict test uses external edit (user edits group in Fastmail UI) rather than timing-dependent race"
  - "Each test script is standalone and runnable independently"
  - "Cleanup is manual (user deletes test contacts) to allow visual verification first"
  - "Discovery URL fixed from / to /.well-known/carddav for proper CardDAV discovery"

patterns-established:
  - "CardDAV human test pattern: connect, validate_groups, exercise operation, PASS/FAIL with step-level reporting"
  - "Interactive pause for manual Fastmail verification between automated steps"

requirements-completed: [CDAV-01, CDAV-02, CDAV-03, CDAV-04, CDAV-05]

# Metrics
duration: 3min
completed: 2026-02-24
---

# Phase 2 Plan 3: Human Validation Test Scripts Summary

**Three human test scripts validated CardDAV auth, contact CRUD, duplicate prevention, and group membership with ETag conflict handling against live Fastmail -- Phase 2 validation gate PASSED**

## Performance

- **Duration:** 3 min (Task 1 automation) + user validation time
- **Started:** 2026-02-24T02:47:39Z
- **Completed:** 2026-02-24T10:07:35Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments
- All 3 human test scripts passed against live Fastmail, confirming Phase 2 success criteria
- test_4_carddav_auth.py: validated CardDAV connection, addressbook discovery, and group existence (read-only)
- test_5_carddav_contacts.py: created test contact, searched by email, verified upsert prevents duplicates, visual Fastmail verification
- test_6_carddav_groups.py: created contact, added to group, verified membership via vCard fetch, tested ETag conflict handling with user-triggered group edit
- Discovery URL bug fixed (/.well-known/carddav) and ETag conflict test rewritten to be deterministic during validation

## Task Commits

Each task was committed atomically:

1. **Task 1: Create human test scripts for CardDAV validation** - `80d5d0c` (feat)
2. **Task 2: Validate CardDAV client against live Fastmail** - checkpoint:human-verify (approved by user)

Additional commits during validation:
- `dacf59f` - fix: use /.well-known/carddav for CardDAV discovery
- `5b0c5c8` - feat: deterministic ETag conflict test
- `512d863` - test: observational ETag check in human test 6
- `ec3063e` - revert: remove premature logging from CardDAV client

## Files Created/Modified
- `human-tests/test_4_carddav_auth.py` - CardDAV auth + discovery + group validation test
- `human-tests/test_5_carddav_contacts.py` - Contact create, search, duplicate prevention test
- `human-tests/test_6_carddav_groups.py` - Group membership and ETag conflict test
- `human-tests/.env.example` - Added CardDAV credential placeholders
- `src/mailroom/clients/carddav.py` - Fixed discovery URL to /.well-known/carddav

## Decisions Made
- ETag conflict test uses deterministic approach: user manually edits group in Fastmail UI between steps, then add_to_group fetches fresh vCard with new ETag and succeeds
- Each script is fully standalone (own dotenv loading, connection, validation)
- Cleanup is manual -- user deletes test contacts after visual verification rather than auto-cleanup
- Discovery URL fixed from `/` to `/.well-known/carddav` for correct CardDAV endpoint resolution
- Logging added to add_to_group then reverted per user preference for uniform logging approach in later phase

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed f-string lint warnings (F541)**
- **Found during:** Task 1 (verification)
- **Issue:** Several print statements used f-strings without any placeholders
- **Fix:** Removed extraneous `f` prefix from string literals that had no interpolation
- **Files modified:** human-tests/test_5_carddav_contacts.py, human-tests/test_6_carddav_groups.py
- **Verification:** `uv run ruff check` shows only expected E402 (same as existing human tests)
- **Committed in:** 80d5d0c (Task 1 commit)

**2. [Rule 1 - Bug] Discovery URL incorrect for CardDAV**
- **Found during:** Task 2 (live Fastmail validation)
- **Issue:** CardDAV client used `/` as discovery URL, but Fastmail requires `/.well-known/carddav`
- **Fix:** Changed discovery URL to `/.well-known/carddav` in CardDAV client
- **Files modified:** src/mailroom/clients/carddav.py
- **Verification:** test_4_carddav_auth.py passes against live Fastmail
- **Committed in:** dacf59f

**3. [Rule 1 - Bug] ETag conflict test was non-deterministic**
- **Found during:** Task 2 (live Fastmail validation)
- **Issue:** Original ETag test relied on timing that was unreliable against live Fastmail
- **Fix:** Rewrote to use deterministic external edit approach with user pause
- **Files modified:** human-tests/test_6_carddav_groups.py
- **Verification:** Test passes consistently against live Fastmail
- **Committed in:** 5b0c5c8

---

**Total deviations:** 3 auto-fixed (3 bugs found during live validation)
**Impact on plan:** Discovery URL fix was critical for Fastmail connectivity. ETag test rewrite improved reliability. No scope creep.

## Issues Encountered
- Discovery URL needed to be `/.well-known/carddav` rather than `/` -- discovered during live Fastmail testing, fixed immediately
- Observational ETag step added to confirm Fastmail changes ETags on web UI edits (commit 512d863)
- Logging was added to CardDAV client then reverted (commit ec3063e) per user preference for a uniform logging approach in a later phase

## User Setup Required
Before running human tests, the user must:
1. Create a Fastmail app password with CardDAV access
2. Ensure contact groups exist in Fastmail: Imbox, Feed, Paper Trail, Jail
3. Set MAILROOM_CARDDAV_USERNAME and MAILROOM_CARDDAV_PASSWORD in human-tests/.env

## Next Phase Readiness
- Phase 2 validation gate is PASSED -- all CardDAV operations verified against live Fastmail
- CardDAV client is proven: auth, discovery, contact create, search, duplicate prevention, group membership, ETag conflict handling
- Phase 3 (triage pipeline) can proceed with confidence that the KIND:group contact model works with Fastmail
- Key blocker from Phase 2 context is resolved: "CardDAV KIND:group contact model verified against live Fastmail"

## Self-Check: PASSED

All files and commits verified:
- human-tests/test_4_carddav_auth.py: FOUND
- human-tests/test_5_carddav_contacts.py: FOUND
- human-tests/test_6_carddav_groups.py: FOUND
- human-tests/.env.example: FOUND
- src/mailroom/clients/carddav.py: FOUND
- Commit 80d5d0c: FOUND
- Commit dacf59f: FOUND
- Commit 5b0c5c8: FOUND
- Commit 512d863: FOUND
- Commit ec3063e: FOUND

---
*Phase: 02-carddav-client-validation-gate*
*Completed: 2026-02-24*
