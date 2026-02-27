"""JMAP EventSource (SSE) listener for push-triggered triage.

Architecture: The SSE listener runs in a daemon thread, pushes lightweight
"state_changed" signals to a queue.Queue. It never calls the workflow
directly -- it only signals that something changed. The main thread owns
all poll() calls.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable

import httpx
import structlog


def drain_queue(q: queue.Queue) -> int:
    """Drain all pending items from queue. Returns count drained."""
    count = 0
    while True:
        try:
            q.get_nowait()
            count += 1
        except queue.Empty:
            return count


def sse_listener(
    token: str,
    event_source_url: str,
    event_queue: queue.Queue,
    shutdown_event: threading.Event,
    log: structlog.BoundLogger | None = None,
    health_cls: type | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> None:
    """Listen for JMAP EventSource events, push signals to queue.

    Connects to the Fastmail EventSource endpoint with Bearer auth,
    subscribes to Email and Mailbox state changes, and pushes
    "state_changed" signals to the event_queue on each state event.

    Reconnects with exponential backoff on disconnect (1s->2s->4s->...->60s cap).
    Honors server retry: field when present. Detects dead connections via
    httpx read timeout (90s > 2x 30s ping interval). First reconnect is
    logged at DEBUG (expected timeout); subsequent failures at WARNING.

    Args:
        token: Fastmail API token for Bearer auth.
        event_source_url: Base EventSource URL from JMAP session.
        event_queue: Queue to push "state_changed" signals to.
        shutdown_event: Event to signal graceful shutdown.
        log: Structured logger instance.
        health_cls: Class with SSE health attributes (written for health endpoint).
    """
    if log is None:
        log = structlog.get_logger(component="eventsource")
    if sleep_fn is None:
        sleep_fn = lambda delay: shutdown_event.wait(delay)

    url = f"{event_source_url}?types=Email,Mailbox&closeafter=no&ping=30"
    attempt = 0
    server_retry_ms: int | None = None  # from retry: field

    while not shutdown_event.is_set():
        try:
            with httpx.Client(
                timeout=httpx.Timeout(connect=30.0, read=90.0, write=30.0, pool=30.0)
            ) as http:
                with http.stream(
                    "GET",
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "text/event-stream",
                    },
                ) as response:
                    response.raise_for_status()
                    attempt = 0  # reset on successful connect
                    server_retry_ms = None
                    if health_cls is not None:
                        health_cls.sse_status = "connected"
                        health_cls.sse_connected_since = time.time()
                    log.info("eventsource_connected")

                    for line in response.iter_lines():
                        if shutdown_event.is_set():
                            return
                        if line.startswith("event: state"):
                            event_queue.put("state_changed")
                            if health_cls is not None:
                                health_cls.sse_last_event_at = time.time()
                        elif line.startswith("retry:"):
                            # Honor server-suggested reconnection delay (milliseconds)
                            try:
                                server_retry_ms = int(line.split(":", 1)[1].strip())
                            except (ValueError, IndexError):
                                pass  # ignore malformed retry field

        except Exception as exc:
            if shutdown_event.is_set():
                return
            attempt += 1
            if health_cls is not None:
                health_cls.sse_status = "disconnected"
                health_cls.sse_reconnect_count += 1
                health_cls.sse_last_error = str(exc)
            # Use server retry if available, otherwise exponential backoff
            if server_retry_ms is not None:
                delay = server_retry_ms / 1000.0
            else:
                delay = min(2 ** attempt, 60)
            log_fn = log.debug if attempt <= 1 else log.warning
            log_fn(
                "eventsource_disconnected",
                retry_in=delay,
                attempt=attempt,
                error=str(exc),
            )
            sleep_fn(delay)

    log.info("eventsource_stopped")
