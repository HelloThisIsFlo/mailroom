# Quick Task 2: Adjust logging levels of certain messages - Context

**Gathered:** 2026-03-05
**Status:** Ready for planning

<domain>
## Task Boundary

Adjust logging levels of certain messages to reduce noise in production Kubernetes logs while preserving visibility into meaningful events.

</domain>

<decisions>
## Implementation Decisions

### Poll noise — poll_completed level
- **Decision:** Use conditional logging: `trigger == "push"` stays at `info`, `scheduled` and `fallback` become `debug`
- **Rationale:** Production logs showed 76/80 lines were scheduled poll_completed heartbeats, burying the 4 meaningful triage lines. Push-triggered polls correlate with real mail events and confirm SSE is working, so they remain visible at info level.
- **Evidence:** Reviewed live k8s logs — the triage of hello@setapp.com into Billboard was nearly invisible among scheduled polls.

### Workflow detail events (contact_upserted, ancestor_group_added, triage_complete)
- **Decision:** Claude's Discretion — keep at info
- **Rationale:** These only fire when actual triage happens (not every poll), so they're already low-volume and high-signal.

### Lifecycle events (service_started, eventsource_connected, etc.)
- **Decision:** Claude's Discretion — keep at info
- **Rationale:** Startup/shutdown events are rare and useful for debugging pod restarts.

</decisions>

<specifics>
## Specific Ideas

- The screener's `poll_complete` already follows the right pattern: debug when empty, info when work done (lines 49 vs 75 in screener.py)
- Only `__main__.py:213` needs changing — the `poll_completed` event in the main polling loop
- No other log statements need level changes

</specifics>
