---
phase: 08-eventsource-push
plan: 01
subsystem: api
tags: [sse, eventsource, jmap, httpx, threading, queue]

# Dependency graph
requires:
  - phase: 01-foundation-and-jmap-client
    provides: JMAPClient session discovery, httpx patterns
  - phase: 06-configurable-categories
    provides: MailroomSettings with pydantic-settings
provides:
  - SSE listener function (sse_listener) with reconnection and backoff
  - drain_queue helper for debounce consumption
  - MailroomSettings.debounce_seconds config field
  - MailroomSettings.poll_interval lowered to 60s default
  - JMAPClient.event_source_url property from JMAP session
affects: [08-eventsource-push plan 02 main loop integration]

# Tech tracking
tech-stack:
  added: []
  patterns: [SSE streaming with httpx, threaded listener with queue signaling, exponential backoff with cap]

key-files:
  created:
    - src/mailroom/eventsource.py
    - tests/test_eventsource.py
  modified:
    - src/mailroom/core/config.py
    - src/mailroom/clients/jmap.py
    - tests/test_config.py
    - tests/test_jmap_client.py

key-decisions:
  - "SSE listener uses httpx streaming (not aiohttp) for consistency with existing JMAP client"
  - "Relaxed pytest-httpx assertions for SSE tests due to reconnection race conditions"
  - "Backoff formula: min(2**attempt, 60) -- simple, no jitter needed for single client"

patterns-established:
  - "SSE listener: daemon thread pushes signals to queue, never calls workflow directly"
  - "pytest-httpx _RELAXED marker for tests with reconnection behavior"

requirements-completed: [PUSH-01, PUSH-02, PUSH-03, PUSH-04]

# Metrics
duration: 5min
completed: 2026-02-27
---

# Phase 8 Plan 01: EventSource Core Components Summary

**SSE listener with exponential backoff reconnection, drain_queue helper, debounce_seconds config, and JMAPClient eventSourceUrl property**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-27T11:00:02Z
- **Completed:** 2026-02-27T11:05:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- SSE listener function with Bearer auth, state event detection, ping filtering, and clean shutdown
- Exponential backoff reconnection (1s->2s->4s->...->60s cap) honoring server retry: field
- drain_queue helper for debounce queue consumption
- Config additions: debounce_seconds=3, poll_interval lowered from 300 to 60
- JMAPClient.event_source_url property extracting URL from JMAP session
- 19 new tests (6 config/jmap + 13 eventsource), 272 total tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Config additions and JMAPClient eventSourceUrl** - `d2e8a0d` (feat)
2. **Task 2: TDD SSE listener function** - RED: `bfb1357` (test), GREEN: `ac9760e` (feat)

## Files Created/Modified
- `src/mailroom/eventsource.py` - SSE listener function and drain_queue helper
- `src/mailroom/core/config.py` - debounce_seconds field, lowered poll_interval default
- `src/mailroom/clients/jmap.py` - event_source_url property from JMAP session
- `tests/test_eventsource.py` - 13 tests for SSE listener, reconnection, backoff, drain_queue
- `tests/test_config.py` - 3 new tests for debounce_seconds and poll_interval default
- `tests/test_jmap_client.py` - 3 new tests for event_source_url property

## Decisions Made
- SSE listener uses httpx streaming for consistency with existing JMAP client (no new HTTP library needed)
- Used relaxed pytest-httpx assertions (_RELAXED marker) for SSE tests because the reconnection loop can fire an extra request between event delivery and shutdown
- Backoff formula min(2**attempt, 60) is simple and sufficient for a single-client scenario

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test patterns for SSE listener threading with pytest-httpx**
- **Found during:** Task 2 (GREEN phase)
- **Issue:** Plan's test approach set shutdown_event before starting the thread, causing the listener to exit before processing any events. Also, pytest-httpx strict assertions failed when the listener's reconnection loop made unexpected requests.
- **Fix:** Restructured tests to start thread first, wait for events via queue.get(timeout=5), then set shutdown. Added _RELAXED marker (assert_all_requests_were_expected=False, assert_all_responses_were_requested=False) for tests with reconnection behavior. Used get_requests() instead of get_request() for tests that may have multiple requests.
- **Files modified:** tests/test_eventsource.py
- **Verification:** All 13 eventsource tests pass reliably
- **Committed in:** ac9760e (GREEN phase commit)

---

**Total deviations:** 1 auto-fixed (1 bug in test patterns)
**Impact on plan:** Test patterns adjusted for threading + httpx mock interaction. All behaviors from the plan are tested. No scope creep.

## Issues Encountered
None beyond the test pattern adjustment documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All SSE building blocks ready for Plan 02 to wire into the main loop
- sse_listener(), drain_queue(), debounce_seconds config, event_source_url property all available
- Plan 02 will integrate these into __main__.py with thread management and health status

---
*Phase: 08-eventsource-push*
*Completed: 2026-02-27*
