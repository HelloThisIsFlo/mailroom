# EventSource Integration Sketch

How to migrate from polling to EventSource-triggered triage, with code snippets showing exactly where things change.

## Current Architecture (Polling)

The main loop in `__main__.py` is straightforward:

```python
# __main__.py lines 123-142
while not shutdown_event.is_set():
    workflow.poll()
    shutdown_event.wait(settings.poll_interval)  # sleep 300s
```

`workflow.poll()` is a pure function — it queries for triaged emails, processes them, returns. It has no opinion about *when* it's called. This is good news: we don't need to touch the workflow at all.

## What Changes

Only two files need meaningful changes:

| File | Change |
|------|--------|
| `clients/jmap.py` | Store `eventSourceUrl` from session during `connect()` |
| `__main__.py` | Replace fixed sleep with SSE listener + debounce |

The workflow, config, CardDAV client, and all business logic stay untouched.

## 1. Capture `eventSourceUrl` in JMAPClient

`connect()` already fetches the session. We just need to keep one more field:

```python
# jmap.py — connect() currently does:
data = resp.json()
self._account_id = data["primaryAccounts"]["urn:ietf:params:jmap:mail"]
self._api_url = data["apiUrl"]

# Add one line:
self._event_source_url = data.get("eventSourceUrl")
```

Expose it as a property:

```python
@property
def event_source_url(self) -> str | None:
    return self._event_source_url
```

That's it for the client. No new dependencies, no behavior change.

## 2. Replace the Main Loop

The current loop is:

```
while running:
    poll()
    sleep(300s)
```

The new loop becomes:

```
start SSE listener thread → writes to a queue
start debounce thread     → reads queue, triggers poll after 3s quiet
keep polling every 300s as fallback
```

### The SSE Listener

A thread that holds the EventSource connection open and pushes events to a queue:

```python
import queue
import threading

def _sse_listener(
    token: str,
    event_source_url: str,
    event_queue: queue.Queue,
    shutdown_event: threading.Event,
    log,
) -> None:
    """Listen for JMAP EventSource events, push relevant ones to queue."""
    url = f"{event_source_url}?types=Email,Mailbox&closeafter=no&ping=30"

    while not shutdown_event.is_set():
        try:
            with httpx.Client(
                timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)
            ) as http:
                with http.stream(
                    "GET", url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "text/event-stream",
                    },
                ) as response:
                    response.raise_for_status()
                    log.info("eventsource_connected")

                    for line in response.iter_lines():
                        if shutdown_event.is_set():
                            return
                        # We only care that *something* changed, not what.
                        # Any "event: state" line means mailbox or email state moved.
                        if line.startswith("event: state"):
                            event_queue.put("state_changed")

        except Exception:
            if shutdown_event.is_set():
                return
            log.warning("eventsource_disconnected", exc_info=True)
            # Exponential backoff would go here (1s, 2s, 4s, max 60s)
            shutdown_event.wait(5)  # simple retry delay for sketch
```

Key points:
- Subscribes to `Email,Mailbox` only (not `*`) — we don't care about ContactCard changes
- Pushes a simple signal to the queue, not the full event data (we don't need state strings)
- Reconnects on any error with a delay
- Respects `shutdown_event` for clean exit

### The Debounced Main Loop

```python
def main() -> None:
    # ... existing startup (connect, resolve mailboxes, build workflow) ...

    shutdown_event = threading.Event()
    event_queue: queue.Queue = queue.Queue()

    # Start SSE listener thread
    if jmap.event_source_url:
        sse_thread = threading.Thread(
            target=_sse_listener,
            args=(settings.jmap_token, jmap.event_source_url, event_queue, shutdown_event, log),
            daemon=True,
        )
        sse_thread.start()
        log.info("eventsource_listener_started")

    DEBOUNCE_SECONDS = 3
    FALLBACK_POLL_SECONDS = settings.poll_interval  # 300s

    while not shutdown_event.is_set():
        # Wait for either an SSE event or the fallback poll timer
        try:
            event_queue.get(timeout=FALLBACK_POLL_SECONDS)
            # Got an SSE event — drain any queued events and debounce
            _drain_queue(event_queue)
            shutdown_event.wait(DEBOUNCE_SECONDS)
            _drain_queue(event_queue)  # drain events that arrived during debounce
        except queue.Empty:
            # Fallback: no SSE event within poll_interval, poll anyway
            pass

        if shutdown_event.is_set():
            break

        try:
            workflow.poll()
            consecutive_failures = 0
            HealthHandler.last_successful_poll = time.time()
        except Exception:
            consecutive_failures += 1
            # ... existing error handling ...


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

### How It Behaves

| Scenario | What happens |
|----------|-------------|
| Email arrives | SSE fires within ~1s → debounce 3s → `poll()` runs |
| 5 emails arrive rapidly | SSE fires 5 times within milliseconds → debounce collapses them → single `poll()` |
| User applies triage label | SSE fires (Mailbox state change) → debounce → `poll()` picks it up |
| SSE connection drops | No queue events → fallback triggers `poll()` after 300s (as before) |
| Nothing happens for 5 min | Queue timeout → fallback `poll()` runs (as before) |
| Graceful shutdown (SIGTERM) | `shutdown_event` wakes all waits → clean exit |

## 3. Caveats

### SSE Read Timeout

The `read=300.0` timeout on the httpx client means the SSE connection will time out after 5 minutes of silence. With `ping=30`, Fastmail sends a keepalive every 30s, so this should never trigger during normal operation. But if pings stop (server issue), the timeout ensures we don't hang forever. The listener reconnects automatically.

### Thread Safety

`workflow.poll()` always runs on the main thread, never concurrently. The SSE listener only puts items in the queue — it never calls the workflow. So there's no shared mutable state between threads beyond the queue (which is thread-safe) and the shutdown event.

### No State Tracking Needed

We don't need to track JMAP state strings from the events. The workflow already queries for *all* triaged emails on every poll. If we miss an event or process a stale one, the worst case is an extra no-op poll. The existing retry design (triage label removed last) means nothing is lost.

### Health Check Impact

The health endpoint checks `last_successful_poll` freshness against `2 * poll_interval`. With EventSource, polls happen more frequently (within seconds of changes), so the health check will actually be *more* responsive. No change needed.

### Graceful Degradation

If `event_source_url` is `None` (unlikely, but possible with a different JMAP server), the listener thread simply doesn't start. The loop falls back to pure polling. Zero behavior change for non-EventSource servers.

### Config Addition

One new optional config field:

```python
# config.py
debounce_seconds: int = 3  # EventSource debounce window
```

Exposed as `MAILROOM_DEBOUNCE_SECONDS`. Default 3 is fine for most cases, but configurable if empirical testing shows different clustering.

## 4. What Does NOT Change

- `ScreenerWorkflow.poll()` — untouched, it's still the same pure triage cycle
- `CardDAVClient` — no involvement in push notifications
- `JMAPClient.call()`, `query_emails()`, etc. — SSE is a separate HTTP connection
- Config labels, mailboxes, groups — all unchanged
- Human integration tests — they call `workflow.poll()` directly, unaffected
- Health endpoint — works as before, just gets fresher timestamps
- Graceful shutdown — same SIGTERM/SIGINT pattern, SSE thread is daemon

## 5. Rough Estimate of Diff Size

- `jmap.py`: +5 lines (store + expose `eventSourceUrl`)
- `__main__.py`: ~+50 lines (SSE listener function, debounce logic, thread start)
- `config.py`: +1 line (optional `debounce_seconds` field)
- New test: ~30 lines (mock SSE stream, verify debounce collapses events)

Total: ~90 lines of new code. No refactoring of existing code.
