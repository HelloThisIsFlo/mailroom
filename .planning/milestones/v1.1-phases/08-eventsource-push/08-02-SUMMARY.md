---
phase: 08-eventsource-push
plan: 02
subsystem: api
tags: [sse, eventsource, jmap, queue, debounce, push, health]

# Dependency graph
requires:
  - phase: 08-eventsource-push
    plan: 01
    provides: sse_listener function, drain_queue helper, debounce_seconds config, JMAPClient.event_source_url
  - phase: 04-packaging-and-deployment
    provides: __main__.py polling service structure, HealthHandler
provides:
  - Queue-based debounced main loop (push-triggered + fallback polling)
  - SSE listener thread startup on service boot
  - Health endpoint with EventSource status object (5 fields)
  - Trigger source in poll log entries (push vs fallback)
  - Human integration test for push-triggered triage latency
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [queue.get(timeout) for combined event+timer wait, class-level health attributes for cross-thread reporting, debounce with drain-wait-drain pattern]

key-files:
  created:
    - human-tests/test_16_eventsource_push.py
  modified:
    - src/mailroom/__main__.py
    - src/mailroom/eventsource.py
    - tests/test_eventsource.py

key-decisions:
  - "health_cls parameter passed as class reference to sse_listener (avoids circular import)"
  - "Overall health status NOT degraded when SSE is down (only poll staleness matters)"
  - "Debounce uses drain-wait-drain pattern: drain queue, wait debounce_seconds, drain again to collapse rapid events"

patterns-established:
  - "Cross-thread health reporting: class-level attributes on HealthHandler (written by SSE thread, read by health endpoint)"
  - "Queue-based combined wait: queue.get(timeout=poll_interval) replaces shutdown_event.wait() for dual-source wake"

requirements-completed: [PUSH-05, PUSH-06]

# Metrics
duration: 3min
completed: 2026-02-27
---

# Phase 8 Plan 02: Main Loop Integration Summary

**Queue-based debounced main loop with SSE thread, health endpoint EventSource status, trigger-tagged poll logging, and human latency test**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-27T11:07:19Z
- **Completed:** 2026-02-27T11:10:47Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- HealthHandler extended with 5 SSE status class-level attributes, exposed in /healthz eventsource object
- sse_listener updated with health_cls parameter for cross-thread health reporting (backward compatible)
- Main loop replaced with queue.get(timeout=poll_interval) for combined push/fallback, debounce with drain-wait-drain
- SSE listener daemon thread starts when eventSourceUrl is available
- Poll log entries include trigger=push (SSE) or trigger=fallback (timeout)
- Human integration test for push-triggered triage latency (test_16_eventsource_push.py)
- 4 new unit tests for health status reporting, 276 total tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Add health SSE status and update sse_listener for health reporting** - `cba4437` (feat)
2. **Task 2: Replace main loop with queue-based debounced loop and SSE thread startup** - `eb39e11` (feat)
3. **Task 3: Create human integration test for push-triggered triage latency** - `6c41795` (feat)

## Files Created/Modified
- `src/mailroom/__main__.py` - Queue-based debounced main loop, SSE thread startup, health endpoint with eventsource status
- `src/mailroom/eventsource.py` - health_cls parameter for cross-thread health status reporting
- `tests/test_eventsource.py` - 4 new tests for health status (connect, event, disconnect, backward compat)
- `human-tests/test_16_eventsource_push.py` - End-to-end latency test for push-triggered triage

## Decisions Made
- health_cls passed as class reference to sse_listener to avoid circular import between __main__.py and eventsource.py
- Overall health status NOT degraded when SSE is down -- only poll staleness matters for liveness (SSE pings are keepalives, not state events)
- Debounce uses drain-wait-drain pattern to collapse rapid events during the debounce window

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 8 (EventSource Push) is now complete
- All SSE components wired into the main loop
- Push-triggered polling operational when Fastmail provides eventSourceUrl
- Fallback polling continues at poll_interval when SSE unavailable
- Human test ready for manual latency verification

## Self-Check: PASSED

All files verified present. All 3 task commits verified in git log.

---
*Phase: 08-eventsource-push*
*Completed: 2026-02-27*
