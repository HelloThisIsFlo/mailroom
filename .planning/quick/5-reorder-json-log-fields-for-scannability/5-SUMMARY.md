---
phase: quick-5
plan: 01
subsystem: logging
tags: [structlog, json, observability]

requires:
  - phase: 01-foundation
    provides: structlog logging module
provides:
  - reorder_keys processor for consistent JSON field ordering
affects: []

tech-stack:
  added: []
  patterns: [priority-key reordering in structlog processor chain]

key-files:
  created: []
  modified:
    - src/mailroom/core/logging.py
    - tests/test_logging.py

key-decisions:
  - "reorder_keys inserted in JSON path only (after dict_tracebacks, before JSONRenderer) -- TTY/console path unchanged"

patterns-established:
  - "Priority key ordering: timestamp, level, component, event, then remaining context"

requirements-completed: [TODO-13]

duration: 1min
completed: 2026-02-28
---

# Quick Task 5: Reorder JSON Log Fields for Scannability Summary

**structlog reorder_keys processor puts timestamp/level/component/event first in JSON output for scannable kubectl/docker logs**

## Performance

- **Duration:** 1 min
- **Started:** 2026-02-28T17:05:12Z
- **Completed:** 2026-02-28T17:06:22Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- Added reorder_keys structlog processor with configurable priority keys tuple
- JSON log output now consistently starts with timestamp, level, component (when present), event
- Console/TTY logging path completely unaffected
- 4 new tests: unit tests for reorder_keys processor, integration tests for JSON field ordering

## Task Commits

Each task was committed atomically (TDD):

1. **Task 1 RED: Failing tests for field ordering** - `35bf60f` (test)
2. **Task 1 GREEN: Implement reorder_keys processor** - `23a3f41` (feat)

## Files Created/Modified
- `src/mailroom/core/logging.py` - Added _PRIORITY_KEYS tuple and reorder_keys processor function, inserted into JSON processor chain
- `tests/test_logging.py` - Added test_reorder_keys_processor, test_reorder_keys_without_component, test_json_field_order_with_component, test_json_field_order_without_component

## Decisions Made
- reorder_keys inserted only in JSON/prod path (after dict_tracebacks, before JSONRenderer) -- ConsoleRenderer handles its own formatting

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- JSON logs now have consistent field ordering for scanning
- No further action needed

## Self-Check: PASSED

- All files verified present (src/mailroom/core/logging.py, tests/test_logging.py, 5-SUMMARY.md)
- All commits verified (35bf60f, 23a3f41)
- All 9 tests passing
- Smoke test field ordering verified

---
*Quick Task: 5-reorder-json-log-fields-for-scannability*
*Completed: 2026-02-28*
