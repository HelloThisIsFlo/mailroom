---
phase: 14-contact-provenance-tracking-for-clean-reset
plan: 03
subsystem: reset, carddav, jmap
tags: [carddav, jmap, provenance, reset, vcard, user-modification-detection]

# Dependency graph
requires:
  - phase: 14-contact-provenance-tracking-for-clean-reset
    provides: MailroomSectionSettings with provenance_group, infrastructure_groups, provenance note format
provides:
  - delete_contact() on CardDAVClient (HTTP DELETE with ETag concurrency)
  - batch_add_labels() on JMAPClient (mirror of batch_remove_labels using True)
  - _is_user_modified() vCard field detection
  - Provenance-aware reset with three-way contact classification (delete/warn/strip)
  - 7-step operation order in apply_reset matching CONTEXT.md spec
  - Updated reporting with DELETE/WARN/strip sections
affects: [human-tests, reset-cli]

# Tech tracking
tech-stack:
  added: []
  patterns: [provenance-aware three-way contact classification, 7-step idempotent reset order]

key-files:
  created: []
  modified:
    - src/mailroom/clients/carddav.py
    - src/mailroom/clients/jmap.py
    - src/mailroom/reset/resetter.py
    - src/mailroom/reset/reporting.py
    - tests/test_resetter.py
    - tests/test_carddav_client.py
    - tests/test_jmap_client.py

key-decisions:
  - "User-modified detection checks vCard fields beyond Mailroom's managed set (version, uid, fn, n, email, note, org, prodid)"
  - "Apple x-addressbookserver-* fields ignored in user-modification check (system fields, not user data)"
  - "Step 6 strips notes from delete targets too (safety: if step 7 fails, contact at least has note cleaned)"
  - "batch_add_labels mirrors batch_remove_labels exactly, using True instead of None in JMAP patch"

patterns-established:
  - "Three-way provenance classification: created_unmodified -> DELETE, created_modified -> WARN, adopted -> strip"
  - "7-step reset order: labels, system-label cleanup, group removal, warning application, provenance removal, note strip, contact delete"

requirements-completed: [PROV-08, PROV-09, PROV-10, PROV-11]

# Metrics
duration: 7min
completed: 2026-03-04
---

# Phase 14 Plan 03: Provenance-Aware Reset Summary

**Deterministic provenance-based reset: DELETE unmodified created contacts, WARN user-modified created contacts with @MailroomWarning, strip-only adopted contacts, exact 7-step operation order**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-04T14:49:16Z
- **Completed:** 2026-03-04T14:56:38Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- delete_contact() on CardDAVClient sends HTTP DELETE with If-Match ETag concurrency control
- batch_add_labels() on JMAPClient adds mailbox labels using JMAP patch syntax (mirror of batch_remove_labels)
- _is_user_modified() detects user-added vCard fields beyond Mailroom's managed set (TEL, ADR, URL, PHOTO, BDAY, TITLE, NICKNAME, extra EMAIL)
- Provenance-aware plan_reset classifies contacts into three lists: delete (provenance + unmodified), warn (provenance + modified), strip (adopted)
- apply_reset follows exact 7-step operation order from CONTEXT.md
- Reporting shows separate DELETE/WARN/strip sections instead of old "Likely Mailroom-Created" hint
- Second reset after warned contacts: contacts are invisible (no provenance group, no Mailroom note)

## Task Commits

Each task was committed atomically (TDD: test then feat):

1. **Task 1: CardDAV delete_contact + JMAP batch_add_labels + user-modified detection**
   - `2f3cc49` (test: add failing tests)
   - `8f007d9` (feat: implement delete_contact, batch_add_labels, _is_user_modified)
2. **Task 2: Provenance-aware reset with 7-step operation order**
   - `3bca73c` (test: add failing tests for provenance-aware reset)
   - `25fc056` (feat: provenance-aware reset with 7-step order)

## Files Created/Modified
- `src/mailroom/clients/carddav.py` - Added delete_contact() method with HTTP DELETE + If-Match
- `src/mailroom/clients/jmap.py` - Added batch_add_labels() method mirroring batch_remove_labels with True patch
- `src/mailroom/reset/resetter.py` - Restructured ContactCleanup (provenance field), ResetPlan (three lists), ResetResult (deleted/warned counters), 7-step apply_reset, _is_user_modified detection
- `src/mailroom/reset/reporting.py` - Updated for provenance-aware sections: DELETE, WARN, strip (replaced old likely-created hint)
- `tests/test_resetter.py` - Rewrote all tests for new structure: provenance classification, 7-step order, second-reset invisibility, reporting sections
- `tests/test_carddav_client.py` - Added delete_contact tests (HTTP DELETE, error handling)
- `tests/test_jmap_client.py` - Added batch_add_labels tests (True patch, notUpdated error)

## Decisions Made
- User-modified detection checks for vCard fields beyond Mailroom's managed set: version, uid, fn, n, email, note, org, prodid. Anything else = user data.
- Apple x-addressbookserver-* fields treated as system fields, not user modification.
- Step 6 intentionally strips notes from delete targets before step 7 deletes them -- safety net for partial failure.
- batch_add_labels is an exact structural mirror of batch_remove_labels, only difference is True vs None in JMAP patch values.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing test assertions for new dataclass structure**
- **Found during:** Task 2 (provenance-aware reset structure)
- **Issue:** Existing tests used old ContactCleanup (likely_created field) and ResetPlan (contacts_to_clean list). All needed updating for new provenance/email fields and three-way classification.
- **Fix:** Rewrote all test helpers and assertions for new structure. Updated _make_contact to include proper vcard_data with EMAIL field.
- **Files modified:** tests/test_resetter.py
- **Verification:** All 31 resetter tests pass
- **Committed in:** 25fc056 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug -- test expectation updates for intentional structure change)
**Impact on plan:** Necessary for correctness after intentional dataclass restructuring. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 14 complete: config rename, provenance tracking, provenance-aware reset
- Full provenance pipeline operational: create_contact adds to provenance group, reset classifies by provenance
- Human integration tests should be updated to cover provenance reset behavior

## Self-Check: PASSED

All files exist. All commits verified (2f3cc49, 8f007d9, 3bca73c, 25fc056). Full test suite: 416 passed.

---
*Phase: 14-contact-provenance-tracking-for-clean-reset*
*Completed: 2026-03-04*
