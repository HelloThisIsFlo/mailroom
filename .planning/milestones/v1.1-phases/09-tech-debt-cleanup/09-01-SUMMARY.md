---
phase: 09-tech-debt-cleanup
plan: 01
subsystem: config, testing, api
tags: [human-tests, deployment, env-vars, configmap, dead-code]

# Dependency graph
requires:
  - phase: 06-configurable-categories
    provides: label_to_category_mapping API replacing label_to_group_mapping
  - phase: 08-eventsource-push
    provides: SSE push as primary, poll_interval=60 default, debounce_seconds
provides:
  - Human tests 3, 7-12 using current v1.1 settings API
  - Deployment artifacts (.env.example, k8s/configmap.yaml) matching current config schema
  - JMAPClient cleaned of unused session_capabilities code
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - human-tests/test_3_label.py
    - human-tests/test_7_screener_poll.py
    - human-tests/test_8_conflict_detection.py
    - human-tests/test_9_already_grouped.py
    - human-tests/test_10_retry_safety.py
    - human-tests/test_11_person_contact.py
    - human-tests/test_12_company_contact.py
    - .env.example
    - k8s/configmap.yaml
    - src/mailroom/clients/jmap.py
    - tests/test_jmap_client.py

key-decisions:
  - "Hardcoded label strings (@ToImbox, @ToPerson) in human tests instead of settings properties -- simpler for standalone scripts"

patterns-established: []

requirements-completed: []

# Metrics
duration: 3min
completed: 2026-02-28
---

# Phase 9 Plan 1: Stale References & Dead Code Cleanup Summary

**Fixed 7 human tests with stale v1.0 API references, synced deployment artifacts to v1.1 config schema, removed unused session_capabilities from JMAPClient**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-28T00:52:00Z
- **Completed:** 2026-02-28T00:54:39Z
- **Tasks:** 3
- **Files modified:** 11

## Accomplishments
- Updated human tests 3, 7-12 to use label_to_category_mapping (attribute access) instead of deleted label_to_group_mapping (dict access)
- Replaced 9 stale individual label/group env vars in .env.example and k8s/configmap.yaml with MAILROOM_TRIAGE_CATEGORIES, DEBOUNCE_SECONDS, and updated POLL_INTERVAL=60
- Removed session_capabilities property, backing field, and 2 associated tests from JMAPClient (dead code since no downstream consumer)

## Task Commits

Each task was committed atomically:

1. **Task 1: Update human tests 3, 7-12 to use current settings API** - `a992b99` (fix)
2. **Task 2: Sync deployment artifacts to current config schema** - `f7ea3a2` (fix)
3. **Task 3: Remove dead session_capabilities code from JMAPClient** - `35075f7` (refactor)

## Files Created/Modified
- `human-tests/test_3_label.py` - Replaced settings.label_to_imbox with hardcoded "@ToImbox"
- `human-tests/test_7_screener_poll.py` - Replaced label_to_group_mapping dict access with label_to_category_mapping attribute access
- `human-tests/test_8_conflict_detection.py` - Same label_to_category_mapping fix
- `human-tests/test_9_already_grouped.py` - Fixed both mailbox list and group lookup (dict["group"] to .contact_group)
- `human-tests/test_10_retry_safety.py` - Same label_to_category_mapping fix
- `human-tests/test_11_person_contact.py` - Fixed label_to_category_mapping + replaced settings.label_to_person with "@ToPerson"
- `human-tests/test_12_company_contact.py` - Fixed label_to_category_mapping + replaced settings.label_to_imbox with "@ToImbox"
- `.env.example` - Removed 9 deleted vars, added TRIAGE_CATEGORIES/DEBOUNCE_SECONDS, updated POLL_INTERVAL=60
- `k8s/configmap.yaml` - Removed 9 deleted vars, added DEBOUNCE_SECONDS/TRIAGE_CATEGORIES, updated POLL_INTERVAL=60
- `src/mailroom/clients/jmap.py` - Removed _session_capabilities field, property, and connect() assignment
- `tests/test_jmap_client.py` - Removed test_connect_stores_capabilities and test_session_capabilities_empty_before_connect

## Decisions Made
- Used hardcoded label strings ("@ToImbox", "@ToPerson") in human tests instead of accessing settings properties -- human tests are standalone scripts where simplicity beats DRY

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All human tests now reference current v1.1 API -- no more AttributeError risk
- Deployment artifacts are current and ready for use
- JMAPClient is cleaner with no dead code
- Ready for 09-02 (remaining tech debt items)

## Self-Check: PASSED

All 11 modified files verified present. All 3 task commits (a992b99, f7ea3a2, 35075f7) verified in git log.

---
*Phase: 09-tech-debt-cleanup*
*Completed: 2026-02-28*
