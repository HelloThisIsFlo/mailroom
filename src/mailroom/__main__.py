"""Mailroom polling service entry point.

Runs the screener triage pipeline with push-triggered polling via JMAP
EventSource (SSE) and fallback fixed-interval polling:
- EventSource push: SSE state events trigger poll within debounce_seconds
- Fallback polling: queue.get(timeout=poll_interval) ensures triage never stops
- Graceful shutdown on SIGTERM/SIGINT (finish current cycle, then exit)
- HTTP health endpoint on /healthz with EventSource status (daemon thread)
- Tiered error handling: startup crash, transient skip, persistent crash
"""

import json
import queue
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import structlog

from mailroom.clients.carddav import CardDAVClient
from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings
from mailroom.core.logging import configure_logging
from mailroom.eventsource import drain_queue, sse_listener
from mailroom.workflows.screener import ScreenerWorkflow

MAX_CONSECUTIVE_FAILURES = 10
HEALTH_PORT = 8080


class HealthHandler(BaseHTTPRequestHandler):
    """Minimal health endpoint for k8s liveness/readiness probes.

    Class-level attributes are shared with the polling loop via direct
    assignment (HealthHandler.last_successful_poll = time.time()).
    """

    last_successful_poll: float = 0.0
    poll_interval: int = 300
    # EventSource status (written by SSE thread, read by health endpoint)
    sse_status: str = "not_started"
    sse_connected_since: float | None = None
    sse_last_event_at: float | None = None
    sse_reconnect_count: int = 0
    sse_last_error: str | None = None

    def do_GET(self) -> None:
        if self.path == "/healthz":
            age = time.time() - self.last_successful_poll
            # Treat just-started (no poll yet) as healthy
            healthy = self.last_successful_poll == 0.0 or age < (self.poll_interval * 2)
            status = 200 if healthy else 503
            body = json.dumps({
                "status": "ok" if healthy else "unhealthy",
                "last_poll_age_seconds": round(age, 1),
                "eventsource": {
                    "status": self.sse_status,
                    "connected_since": self.sse_connected_since,
                    "last_event_at": self.sse_last_event_at,
                    "reconnect_count": self.sse_reconnect_count,
                    "last_error": self.sse_last_error,
                },
            })
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default access logs."""


def _start_health_server(port: int, poll_interval: int) -> ThreadingHTTPServer:
    """Start the health HTTP server on a daemon thread.

    Args:
        port: TCP port to listen on.
        poll_interval: Polling interval in seconds (for staleness check).

    Returns:
        The running server instance.
    """
    HealthHandler.poll_interval = poll_interval
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main() -> None:
    """Run the Mailroom polling service."""
    # --- Startup sequence (crashes on failure) ---

    # 1. Load config
    settings = MailroomSettings()
    configure_logging(settings.log_level)
    log = structlog.get_logger(component="main")

    # 2. Connect JMAP client
    jmap = JMAPClient(token=settings.jmap_token)
    jmap.connect()

    # 3. Connect CardDAV client
    carddav = CardDAVClient(
        username=settings.carddav_username,
        password=settings.carddav_password,
    )
    carddav.connect()

    # 4. Resolve mailboxes (crashes if any missing)
    mailbox_ids = jmap.resolve_mailboxes(settings.required_mailboxes)

    # 5. Validate contact groups (crashes if any missing)
    carddav.validate_groups(settings.contact_groups)

    # 6. Build workflow
    workflow = ScreenerWorkflow(jmap, carddav, settings, mailbox_ids)

    # 7. Start health server on daemon thread
    _start_health_server(HEALTH_PORT, settings.poll_interval)

    # --- Graceful shutdown ---

    shutdown_event = threading.Event()

    def _handle_signal(signum: int, frame: object) -> None:
        log.info("shutdown_signal_received", signal=signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # 8. Start EventSource listener thread (if available)
    event_queue: queue.Queue = queue.Queue()

    if jmap.event_source_url:
        sse_thread = threading.Thread(
            target=sse_listener,
            args=(
                settings.jmap_token,
                jmap.event_source_url,
                event_queue,
                shutdown_event,
            ),
            kwargs={
                "log": structlog.get_logger(component="eventsource"),
                "health_cls": HealthHandler,
            },
            daemon=True,
        )
        sse_thread.start()
        log.info("eventsource_listener_started", url=jmap.event_source_url)
    else:
        log.info("eventsource_not_available", reason="no eventSourceUrl in session")

    # --- Push-triggered polling loop with fallback ---

    log.info(
        "service_started",
        poll_interval=settings.poll_interval,
        debounce_seconds=settings.debounce_seconds,
        health_port=HEALTH_PORT,
        push_enabled=jmap.event_source_url is not None,
    )
    consecutive_failures = 0

    while not shutdown_event.is_set():
        trigger = "fallback"
        try:
            event_queue.get(timeout=settings.poll_interval)
            # Got SSE event -- drain queue and debounce
            pre_drain = drain_queue(event_queue)
            shutdown_event.wait(settings.debounce_seconds)
            post_drain = drain_queue(event_queue)
            trigger = "push"
            log.debug(
                "debounce_collapsed",
                events_collapsed=1 + pre_drain + post_drain,
            )
        except queue.Empty:
            pass  # Fallback: no SSE event within poll_interval

        if shutdown_event.is_set():
            break

        try:
            workflow.poll()
            consecutive_failures = 0
            HealthHandler.last_successful_poll = time.time()
            log.info("poll_completed", trigger=trigger)
        except Exception:
            consecutive_failures += 1
            log.error(
                "poll_failed",
                consecutive_failures=consecutive_failures,
                trigger=trigger,
                exc_info=True,
            )
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                log.critical(
                    "too_many_consecutive_failures",
                    threshold=MAX_CONSECUTIVE_FAILURES,
                )
                sys.exit(1)

    log.info("service_stopped", reason="shutdown_signal")


if __name__ == "__main__":
    from mailroom.cli import cli

    cli()
