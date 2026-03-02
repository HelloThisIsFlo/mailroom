# Phase 8: EventSource Push - Context

**Gathered:** 2026-02-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace fixed-interval polling with JMAP EventSource (SSE) push notifications. Triage latency drops from up to 5 minutes to under 10 seconds. Automatic fallback to polling if SSE fails. Only scheduling logic changes — `workflow.poll()` and all business logic remain untouched.

</domain>

<decisions>
## Implementation Decisions

### Fallback & degraded mode
- Exponential backoff on disconnect: 1s → 2s → 4s → ... → 60s cap (hardcoded, not configurable)
- Honor server `retry:` field from Fastmail when present; fall back to exponential backoff when absent
- Degraded poll frequency and catch-up-on-reconnect behavior: Claude decides the approach

### Health endpoint
- Rich EventSource status object in /health response: `{ status, connected_since, last_event_at, reconnect_count, last_error }`
- Poll staleness threshold remains at 2x poll_interval (SSE pings are keepalives, not state events — quiet mailbox ≠ broken SSE)
- Whether overall status shows "degraded" when SSE is down, and whether trigger source appears in health: Claude decides

### Logging & trigger visibility
- Poll log entries must include trigger source: `trigger=push` or `trigger=fallback`
- Debounce collapse stats (events received vs polls triggered) logged at DEBUG level only
- SSE reconnect logged as simple "reconnected" event (no gap duration calculation)
- SSE lifecycle logging verbosity (key events vs periodic stats): Claude decides

### Config surface area
- One new config field: `MAILROOM_DEBOUNCE_SECONDS` (default 3)
- Lower existing `MAILROOM_POLL_INTERVAL` default from 300s to 60s (tighter safety net now that push is primary)
- SSE type filter hardcoded to `Email,Mailbox` (not configurable)
- No push toggle, no ping interval config, no read timeout config — keep config surface minimal

### Claude's Discretion
- Degraded poll frequency when SSE is down (increase frequency or keep configured interval)
- Catch-up poll on SSE reconnect (immediate poll vs wait for next event/timer)
- Overall health status degradation when SSE disconnects
- Trigger source in health endpoint response
- SSE lifecycle logging verbosity
- Thread architecture details (daemon threads, queue implementation)

</decisions>

<specifics>
## Specific Ideas

- Integration sketch exists at `.research/jmap-eventsource/integration-sketch.md` — covers SSE listener thread, queue-based debounce, and main loop replacement in detail
- Research at `.research/jmap-eventsource/jmap-eventsource.md` documents Fastmail's EventSource format (envelope with `changed`/`type` keys, `connect` vs `change` event types)
- Discovery script at `.research/jmap-eventsource/eventsource_discovery.py` can be used to validate empirical behavior
- Architecture: SSE listener thread pushes to queue → main thread reads queue with debounce → triggers poll(). Only `__main__.py` and `jmap.py` change meaningfully.
- `workflow.poll()` is a pure idempotent function — no changes needed to business logic

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-eventsource-push*
*Context gathered: 2026-02-27*
