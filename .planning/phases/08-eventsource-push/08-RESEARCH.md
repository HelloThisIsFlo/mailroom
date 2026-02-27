# Phase 8: EventSource Push - Research

**Researched:** 2026-02-27
**Domain:** JMAP EventSource (SSE) push notifications, threading, debounce
**Confidence:** HIGH

## Summary

Phase 8 replaces the fixed-interval polling loop with JMAP EventSource (Server-Sent Events) push notifications. The change is surgically scoped: only `__main__.py` (main loop), `clients/jmap.py` (store `eventSourceUrl`), and `core/config.py` (add `debounce_seconds`, lower `poll_interval` default) require meaningful changes. The workflow, CardDAV client, and all business logic remain untouched because `workflow.poll()` is a pure idempotent function that has no opinion about when it's called.

The architecture is: SSE listener daemon thread pushes signals to a `queue.Queue`, the main thread reads the queue with a configurable debounce window (default 3s), and triggers `poll()`. If no SSE events arrive within `poll_interval`, the queue `.get(timeout=...)` expires and triggers a fallback poll. This means polling never stops -- SSE just makes it faster. Exponential backoff on SSE disconnect (1s to 60s cap) with server `retry:` field honored when present.

**Primary recommendation:** Use raw `httpx.Client.stream()` with `iter_lines()` for SSE parsing (no new dependency), `queue.Queue` + `threading.Event` for cross-thread signaling, and `IteratorStream` from `pytest-httpx` for testing streaming responses.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Exponential backoff on disconnect: 1s -> 2s -> 4s -> ... -> 60s cap (hardcoded, not configurable)
- Honor server `retry:` field from Fastmail when present; fall back to exponential backoff when absent
- Rich EventSource status object in /health response: `{ status, connected_since, last_event_at, reconnect_count, last_error }`
- Poll staleness threshold remains at 2x poll_interval (SSE pings are keepalives, not state events -- quiet mailbox != broken SSE)
- Poll log entries must include trigger source: `trigger=push` or `trigger=fallback`
- Debounce collapse stats (events received vs polls triggered) logged at DEBUG level only
- SSE reconnect logged as simple "reconnected" event (no gap duration calculation)
- One new config field: `MAILROOM_DEBOUNCE_SECONDS` (default 3)
- Lower existing `MAILROOM_POLL_INTERVAL` default from 300s to 60s (tighter safety net now that push is primary)
- SSE type filter hardcoded to `Email,Mailbox` (not configurable)
- No push toggle, no ping interval config, no read timeout config -- keep config surface minimal

### Claude's Discretion
- Degraded poll frequency when SSE is down (increase frequency or keep configured interval)
- Catch-up poll on SSE reconnect (immediate poll vs wait for next event/timer)
- Overall health status degradation when SSE disconnects
- Trigger source in health endpoint response
- SSE lifecycle logging verbosity
- Thread architecture details (daemon threads, queue implementation)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PUSH-01 | SSE listener connects to Fastmail EventSource endpoint with Bearer auth | httpx streaming with `Authorization: Bearer {token}` and `Accept: text/event-stream` headers; URL from session `eventSourceUrl` with `?types=Email,Mailbox&closeafter=no&ping=30` |
| PUSH-02 | State change events trigger triage pass with configurable debounce window (default 3s) | `queue.Queue` + `threading.Event.wait(debounce_seconds)` pattern; drain queue before and after debounce; `MAILROOM_DEBOUNCE_SECONDS` config field |
| PUSH-03 | Liveness detection via ping-based timeout (read timeout > 2x ping interval) | httpx `Timeout(read=90.0)` with `ping=30` gives 3x margin; `ReadTimeout` exception triggers reconnect |
| PUSH-04 | Auto-reconnect with exponential backoff on disconnect (1s -> 2s -> 4s -> max 60s) | Simple `min(2**attempt, 60)` calculation; honor `retry:` field from SSE stream when present; reset attempt counter on successful connect |
| PUSH-05 | Health endpoint reports EventSource connection status and thread liveness | Extend `HealthHandler` class-level attributes with SSE status dict; thread-safe via atomic attribute assignment |
| PUSH-06 | Triage latency reduced from up to 5 minutes to under 10 seconds for push-triggered events | SSE fires within ~1s of action + 3s debounce = ~4s typical latency; human test validates end-to-end |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | (existing) | HTTP streaming for SSE connection | Already in project; `Client.stream()` + `iter_lines()` handles SSE natively |
| threading | stdlib | SSE listener daemon thread | Standard Python threading; `queue.Queue` is thread-safe by design |
| queue | stdlib | Cross-thread event signaling | `Queue.get(timeout=...)` provides both event-driven wake and fallback polling in one call |
| structlog | (existing) | Structured logging with trigger source | Already in project; `log.info("poll_completed", trigger="push")` pattern |
| pydantic-settings | (existing) | `MAILROOM_DEBOUNCE_SECONDS` config field | Already powers all config; just add one field |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-httpx | (existing dev dep) | Mock SSE streaming responses in tests | `IteratorStream([b"event: state\n", b"data: {...}\n", b"\n"])` for mocking SSE |
| time | stdlib | Timestamps for health status, backoff delays | `time.time()` for `connected_since`, `last_event_at` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw httpx `iter_lines()` | `httpx-sse` (0.4.3) library | Adds dependency for SSE parsing; project only needs line detection, not full event object model. Since we ignore event data (just trigger poll on any `event: state` line), raw parsing is simpler. |
| `queue.Queue` debounce | `threading.Event.wait()` with timer reset | Queue approach is cleaner: SSE thread just puts signals, main thread owns all timing logic. No shared mutable state beyond queue. |
| Separate debounce thread | Single main thread with queue timeout | Integration sketch considered 2-thread model but single main thread with `queue.get(timeout=fallback_poll)` + debounce sleep is simpler and matches existing loop structure. |

**Installation:**
```bash
# No new dependencies needed -- all libraries already in project
```

## Architecture Patterns

### Recommended Project Structure
```
src/mailroom/
├── __main__.py         # Main loop: SSE thread start, queue-based debounce, fallback poll
├── clients/jmap.py     # +5 lines: store and expose eventSourceUrl from session
├── core/config.py      # +2 lines: debounce_seconds field, lower poll_interval default
└── (everything else)   # UNCHANGED
```

### Pattern 1: SSE Listener as Daemon Thread
**What:** A daemon thread holds the SSE connection open and pushes lightweight signals to a `queue.Queue`. It never calls the workflow directly -- it only signals that something changed.
**When to use:** When you need a long-lived HTTP connection alongside periodic work on the main thread.
**Example:**
```python
# Source: Integration sketch + RFC 8620 Section 7.3
def _sse_listener(
    token: str,
    event_source_url: str,
    event_queue: queue.Queue,
    shutdown_event: threading.Event,
    health: HealthHandler,  # for status updates
    log: structlog.BoundLogger,
) -> None:
    """Listen for JMAP EventSource events, push signals to queue."""
    url = f"{event_source_url}?types=Email,Mailbox&closeafter=no&ping=30"
    attempt = 0

    while not shutdown_event.is_set():
        try:
            with httpx.Client(
                timeout=httpx.Timeout(connect=30.0, read=90.0, write=30.0, pool=30.0)
            ) as http:
                with http.stream(
                    "GET", url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "text/event-stream",
                    },
                ) as response:
                    response.raise_for_status()
                    attempt = 0  # reset on successful connect
                    log.info("eventsource_connected")
                    # Update health status
                    health.sse_status = "connected"
                    health.sse_connected_since = time.time()

                    for line in response.iter_lines():
                        if shutdown_event.is_set():
                            return
                        if line.startswith("event: state"):
                            event_queue.put("state_changed")
                            health.sse_last_event_at = time.time()
                        elif line.startswith("retry:"):
                            # Honor server-suggested reconnection delay
                            pass  # parse and store

        except Exception:
            if shutdown_event.is_set():
                return
            attempt += 1
            health.sse_status = "disconnected"
            health.sse_reconnect_count += 1
            delay = min(2 ** attempt, 60)
            log.warning("eventsource_disconnected", retry_in=delay)
            shutdown_event.wait(delay)
```

### Pattern 2: Queue-Based Debounced Main Loop
**What:** The main thread uses `queue.get(timeout=poll_interval)` as a combined event wait + fallback timer. On receiving a signal, it drains the queue and waits `debounce_seconds` before polling.
**When to use:** When you need to collapse rapid events into single actions while maintaining a periodic fallback.
**Example:**
```python
# Source: Integration sketch
while not shutdown_event.is_set():
    trigger = "fallback"
    try:
        event_queue.get(timeout=settings.poll_interval)
        # Got SSE event -- drain queue and debounce
        _drain_queue(event_queue)
        shutdown_event.wait(settings.debounce_seconds)
        _drain_queue(event_queue)  # drain arrivals during debounce
        trigger = "push"
    except queue.Empty:
        pass  # Fallback: no SSE event within poll_interval

    if shutdown_event.is_set():
        break

    try:
        workflow.poll()
        log.info("poll_completed", trigger=trigger)
        HealthHandler.last_successful_poll = time.time()
    except Exception:
        # ... existing error handling ...
```

### Pattern 3: Thread-Safe Health Status via Class Attributes
**What:** Extend `HealthHandler` with SSE-specific class-level attributes. The SSE thread writes them, the health endpoint reads them. Simple attribute assignment in CPython is atomic for built-in types.
**When to use:** When health info crosses thread boundaries and full locking is overkill.
**Example:**
```python
class HealthHandler(BaseHTTPRequestHandler):
    last_successful_poll: float = 0.0
    poll_interval: int = 300
    # New SSE fields
    sse_status: str = "not_started"
    sse_connected_since: float | None = None
    sse_last_event_at: float | None = None
    sse_reconnect_count: int = 0
    sse_last_error: str | None = None
```

### Anti-Patterns to Avoid
- **Parsing full SSE event data:** We don't need state strings from events. The workflow already queries all triaged emails on every poll. Parsing `data:` JSON wastes effort and couples us to Fastmail's envelope format.
- **Running poll() from the SSE thread:** Creates concurrency hazards. The SSE thread must only signal; the main thread owns all poll() calls.
- **Using `asyncio` for SSE:** The project is synchronous-by-design (single-user service). Threading is simpler and matches the existing architecture. Async is explicitly out of scope per REQUIREMENTS.md.
- **Tracking JMAP state strings:** The worst case of a stale/duplicate event is an extra no-op poll. The existing retry design (triage label removed last) means nothing is lost.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE line parsing | Full SSE event parser with data concatenation, multi-line data, event ID tracking | Simple `line.startswith("event: state")` check | We only need to detect state change events, not parse their content. The workflow is idempotent. |
| Thread-safe queue | Custom lock-based shared state | `queue.Queue` from stdlib | Queue handles all locking internally. Put from SSE thread, get from main thread. |
| Exponential backoff | Custom timer with jitter calculation | `min(2 ** attempt, 60)` inline | Formula is 3 lines. No need for a library. Jitter not required per user decision. |
| URI template expansion | RFC 6570 template library | Direct query parameter append | Fastmail returns `https://api.fastmail.com/jmap/event/` (plain URL). Append `?types=Email,Mailbox&closeafter=no&ping=30`. See Pitfall 3 below. |

**Key insight:** The architecture's strength is that `workflow.poll()` is completely decoupled from scheduling. We only need to decide *when* to call it. The SSE layer is just a smarter timer -- it doesn't need to understand email content.

## Common Pitfalls

### Pitfall 1: SSE Read Timeout Too Short
**What goes wrong:** httpx `ReadTimeout` fires during normal operation, causing unnecessary reconnects.
**Why it happens:** SSE connections are long-lived. Default httpx timeout (5s) will kill the connection instantly. Even with `ping=30`, network jitter can delay pings.
**How to avoid:** Set `read=90.0` (3x the 30s ping interval). This gives ample margin while still detecting genuinely dead connections.
**Warning signs:** Frequent "eventsource_disconnected" log entries with no actual network issues.

### Pitfall 2: Debounce Sleep Blocks Shutdown
**What goes wrong:** `time.sleep(debounce_seconds)` during debounce window ignores shutdown signals, causing up to 3s delay on SIGTERM.
**Why it happens:** `time.sleep()` is not interruptible by threading events.
**How to avoid:** Use `shutdown_event.wait(debounce_seconds)` instead of `time.sleep()`. The `.wait()` returns immediately when the event is set.
**Warning signs:** Service takes longer than expected to stop during graceful shutdown.

### Pitfall 3: eventSourceUrl Is a URI Template (RFC 6570)
**What goes wrong:** Code treats `eventSourceUrl` as a plain URL and appends `?types=...` directly.
**Why it happens:** RFC 8620 Section 2 says `eventSourceUrl` is in "URI Template (level 1) format" and "MUST contain variables called types, closeafter, and ping." However, Fastmail currently returns a plain URL (`https://api.fastmail.com/jmap/event/`) without template variables.
**How to avoid:** For now, append query parameters directly (as the discovery script does successfully). Add a comment noting the RFC says this should be a URI Template. If Fastmail ever changes to proper templates, this will need updating.
**Warning signs:** 404 responses from the EventSource endpoint (would indicate URL format changed).

### Pitfall 4: Fastmail's Non-Standard Event Envelope
**What goes wrong:** Code looks for standard JMAP `event: state` events but Fastmail uses a different format.
**Why it happens:** Fastmail wraps RFC 8620 state data in an envelope: `{"type": "connect|change", "changed": {...}}`. The `event:` SSE line is `state` but the data format differs from spec.
**How to avoid:** Since we only check `line.startswith("event: state")` and don't parse `data:`, this is a non-issue for our design. But document it for future maintainers.
**Warning signs:** If we ever need event content, the parsing will differ from RFC 8620 examples.

### Pitfall 5: Queue.get() Timeout Resets on Put
**What goes wrong:** Misunderstanding `queue.get(timeout=300)` -- the timeout is from the moment `.get()` is called, not reset when items are added.
**Why it happens:** Developers might expect the timeout to reset like `select()`.
**How to avoid:** This is actually fine for our design. After the first event, we break out of `.get()`, drain, debounce, and poll. The next iteration starts a fresh `.get(timeout=poll_interval)`.
**Warning signs:** None -- just ensure the loop structure handles both paths (event received vs timeout).

### Pitfall 6: Daemon Thread Cleanup
**What goes wrong:** Daemon threads are killed abruptly on process exit, potentially leaving SSE connections half-open.
**Why it happens:** Python kills daemon threads without cleanup when all non-daemon threads exit.
**How to avoid:** Use `shutdown_event` for graceful shutdown. The SSE thread checks `shutdown_event.is_set()` in its loop and after blocking calls. The existing `_handle_signal` function already sets this event. Daemon=True is still correct as a safety net.
**Warning signs:** Fastmail logs showing connections not properly closed (cosmetic issue, not functional).

## Code Examples

Verified patterns from official sources and project context:

### Storing eventSourceUrl in JMAPClient
```python
# Source: Integration sketch -- clients/jmap.py connect()
# Currently:
data = resp.json()
self._account_id = data["primaryAccounts"]["urn:ietf:params:jmap:mail"]
self._api_url = data["apiUrl"]
self._session_capabilities = data.get("capabilities", {})
self._download_url = data.get("downloadUrl")

# Add:
self._event_source_url = data.get("eventSourceUrl")

# New property:
@property
def event_source_url(self) -> str | None:
    return self._event_source_url
```

### Config Addition
```python
# Source: User decision (CONTEXT.md) -- core/config.py
class MailroomSettings(BaseSettings):
    # ... existing fields ...
    poll_interval: int = 60   # lowered from 300 (tighter safety net with push)
    debounce_seconds: int = 3  # EventSource debounce window
```

### Drain Queue Helper
```python
# Source: Integration sketch
def _drain_queue(q: queue.Queue) -> int:
    """Drain all pending items from queue. Returns count drained."""
    count = 0
    while True:
        try:
            q.get_nowait()
            count += 1
        except queue.Empty:
            return count
```

### SSE Event Line Detection
```python
# Source: RFC 8620 + Fastmail empirical observation
# SSE format for JMAP state changes:
#   event: state
#   data: {"changed": {"accountId": {"Email": "state", ...}}, "type": "change"}
#
# We only care about the "event: state" line -- triggers a poll.
# Keepalive pings are comment lines starting with ":"
for line in response.iter_lines():
    if line.startswith("event: state"):
        event_queue.put("state_changed")
    # Ignore: data lines, comment/ping lines, retry lines (handled elsewhere)
```

### Testing SSE with pytest-httpx IteratorStream
```python
# Source: pytest-httpx docs -- verified pattern for streaming responses
from pytest_httpx import HTTPXMock, IteratorStream

def test_sse_listener_pushes_event(httpx_mock: HTTPXMock):
    """SSE state event pushes signal to queue."""
    sse_stream = IteratorStream([
        b"event: state\n",
        b'data: {"changed":{},"type":"change"}\n',
        b"\n",
    ])
    httpx_mock.add_response(
        url="https://api.fastmail.com/jmap/event/?types=Email,Mailbox&closeafter=no&ping=30",
        stream=sse_stream,
        headers={"content-type": "text/event-stream"},
    )
    # ... run listener in thread, check queue has item ...
```

### Exponential Backoff
```python
# Source: User decision (1s -> 2s -> 4s -> max 60s, hardcoded)
attempt = 0
while not shutdown_event.is_set():
    try:
        # ... SSE connection ...
        attempt = 0  # reset on successful connect
    except Exception:
        attempt += 1
        delay = min(2 ** attempt, 60)  # 1, 2, 4, 8, 16, 32, 60, 60, ...
        log.warning("eventsource_disconnected", retry_in=delay)
        shutdown_event.wait(delay)
```

### Health Endpoint SSE Status
```python
# Source: User decision (CONTEXT.md)
body = json.dumps({
    "status": "ok" if healthy else "unhealthy",
    "last_poll_age_seconds": round(age, 1),
    "eventsource": {
        "status": HealthHandler.sse_status,
        "connected_since": HealthHandler.sse_connected_since,
        "last_event_at": HealthHandler.sse_last_event_at,
        "reconnect_count": HealthHandler.sse_reconnect_count,
        "last_error": HealthHandler.sse_last_error,
    },
})
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Fixed-interval polling (300s) | EventSource push + fallback polling (60s) | Phase 8 | Triage latency: 5 min -> ~4 seconds |
| No SSE in JMAP client | `eventSourceUrl` stored from session | Phase 8 | Enables push notifications |
| Health shows poll age only | Health shows poll age + SSE connection status | Phase 8 | Better observability for k8s monitoring |

**Deprecated/outdated:**
- The 300s default `poll_interval` becomes 60s (still configurable, but push is primary trigger now)
- `httpx-sse` library (0.4.3) exists and works well, but adds unnecessary complexity for this use case since we don't need full event parsing

## Open Questions

1. **Fastmail URI Template vs Plain URL**
   - What we know: Fastmail returns `https://api.fastmail.com/jmap/event/` -- a plain URL. Discovery script appends `?types=...` and it works.
   - What's unclear: Whether Fastmail will ever switch to proper RFC 6570 URI Templates with `{types}`, `{closeafter}`, `{ping}` variables.
   - Recommendation: Append query params directly. Add a code comment about the RFC template spec. Low risk of breakage.

2. **SSE Connection Longevity**
   - What we know: Discovery script confirmed connections work with `ping=30` keepalives. Fastmail acknowledged EventSource issues in 2022 but the endpoint works for API tokens.
   - What's unclear: Maximum connection lifetime before Fastmail forces a disconnect (could be hours, days, or unlimited).
   - Recommendation: The reconnection logic handles this transparently. If Fastmail drops the connection, we reconnect with backoff. No special handling needed.

3. **Debounce Window Tuning**
   - What we know: User decided 3s default. Discovery script placeholders for event clustering were not yet filled in.
   - What's unclear: Exact event clustering patterns (batch email arrival timing, label change event timing).
   - Recommendation: 3s is conservative and safe. The debounce_seconds config allows tuning if empirical testing reveals better values.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-httpx |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `pytest tests/ -x` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PUSH-01 | SSE connects with Bearer auth to EventSource URL | unit | `pytest tests/test_eventsource.py::TestSSEListener -x` | Wave 0 |
| PUSH-02 | State events trigger poll with debounce | unit | `pytest tests/test_eventsource.py::TestDebounce -x` | Wave 0 |
| PUSH-03 | Liveness via ping-based read timeout | unit | `pytest tests/test_eventsource.py::TestLiveness -x` | Wave 0 |
| PUSH-04 | Exponential backoff reconnect (1s->60s cap) | unit | `pytest tests/test_eventsource.py::TestReconnect -x` | Wave 0 |
| PUSH-05 | Health reports SSE status | unit | `pytest tests/test_eventsource.py::TestHealthSSE -x` | Wave 0 |
| PUSH-06 | Triage latency < 10s | manual-only | `python human-tests/test_16_eventsource_push.py` | Wave 0 |
| -- | eventSourceUrl stored from session | unit | `pytest tests/test_jmap_client.py::TestConnect::test_connect_stores_event_source_url -x` | Wave 0 |
| -- | debounce_seconds config field | unit | `pytest tests/test_config.py::test_debounce_seconds -x` | Wave 0 |
| -- | poll_interval default lowered to 60 | unit | `pytest tests/test_config.py::test_poll_interval_default -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_eventsource.py` -- new file covering PUSH-01 through PUSH-05 (SSE listener, debounce, backoff, health)
- [ ] `human-tests/test_16_eventsource_push.py` -- end-to-end latency test (apply label, verify triage within 10s)
- [ ] Update `tests/test_jmap_client.py` session response fixture to include `eventSourceUrl`
- [ ] Update `tests/test_config.py` for `debounce_seconds` and new `poll_interval` default

## Sources

### Primary (HIGH confidence)
- [RFC 8620 Section 7.3](https://www.rfc-editor.org/rfc/rfc8620.html) - EventSource push specification, URL format, reconnection guidance
- [httpx official docs](https://www.python-httpx.org/) via Context7 `/encode/httpx` - Streaming responses, `iter_lines()`, timeout configuration
- [pytest-httpx docs](https://colin-b.github.io/pytest_httpx/) - `IteratorStream` for mocking streaming responses
- [Python stdlib queue](https://docs.python.org/3/library/queue.html) - Thread-safe queue, `get(timeout=)` semantics
- [Python stdlib threading](https://docs.python.org/3/library/threading.html) - `Event.wait()`, daemon threads

### Secondary (MEDIUM confidence)
- [httpx-sse 0.4.3](https://pypi.org/project/httpx-sse/) on PyPI (released 2025-10-10) - Verified it exists and works but unnecessary for this use case
- [Fastmail JMAP-Samples Issue #7](https://github.com/fastmail/JMAP-Samples/issues/7) - Confirmed Fastmail's non-standard event envelope format and known deviations from RFC
- [JMAP Crash Course](https://jmap.io/crash-course.html) - Confirmed `eventSourceUrl` value format from Fastmail

### Tertiary (LOW confidence)
- Fastmail connection longevity / rate limiting -- no official documentation found. Inferred from discovery script behavior and community reports that connections work for at least minutes. Long-term behavior unknown.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already in project, well-documented stdlib patterns
- Architecture: HIGH - Integration sketch validated by discovery script, matches project patterns
- Pitfalls: HIGH - Multiple sources cross-referenced (RFC vs Fastmail reality, httpx timeout behavior, threading semantics)

**Research date:** 2026-02-27
**Valid until:** 2026-03-27 (stable domain, no fast-moving dependencies)
