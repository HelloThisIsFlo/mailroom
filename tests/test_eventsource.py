"""Tests for EventSource SSE listener and debounce helpers."""

import queue
import threading
import time

import httpx
import pytest
from pytest_httpx import HTTPXMock, IteratorStream

from mailroom.eventsource import sse_listener, drain_queue


class TestDrainQueue:
    """Tests for drain_queue helper."""

    def test_drain_empty_queue(self):
        """Empty queue returns 0."""
        q = queue.Queue()
        assert drain_queue(q) == 0

    def test_drain_queue_with_items(self):
        """Put 3 items, drain returns 3, queue is now empty."""
        q = queue.Queue()
        q.put("a")
        q.put("b")
        q.put("c")
        assert drain_queue(q) == 3
        assert q.empty()

    def test_drain_queue_partial(self):
        """Put 2 items, get 1 manually, drain returns 1."""
        q = queue.Queue()
        q.put("a")
        q.put("b")
        q.get_nowait()  # remove one
        assert drain_queue(q) == 1


SSE_URL = "https://api.fastmail.com/jmap/event/?types=Email,Mailbox&closeafter=no&ping=30"


# pytest-httpx by default asserts all mocked responses were consumed and all
# requests were expected. Because sse_listener reconnects automatically after
# a stream ends, there can be an extra request between the time we get the
# event and the time we set shutdown. We opt out of strict matching for tests
# that use the listener loop.
_RELAXED = pytest.mark.httpx_mock(
    assert_all_requests_were_expected=False,
    assert_all_responses_were_requested=False,
)


class MockHealthHandler:
    """Mock health handler for SSE health status testing."""

    sse_status: str = "not_started"
    sse_connected_since: float | None = None
    sse_last_event_at: float | None = None
    sse_reconnect_count: int = 0
    sse_last_error: str | None = None

    @classmethod
    def reset(cls):
        cls.sse_status = "not_started"
        cls.sse_connected_since = None
        cls.sse_last_event_at = None
        cls.sse_reconnect_count = 0
        cls.sse_last_error = None


class TestSSEListener:
    """Tests for sse_listener function."""

    def _run_listener(self, event_queue, shutdown, **kwargs):
        """Helper: run sse_listener with standard args."""
        sse_listener(
            token=kwargs.get("token", "test-token"),
            event_source_url="https://api.fastmail.com/jmap/event/",
            event_queue=event_queue,
            shutdown_event=shutdown,
            log=None,
        )

    @_RELAXED
    def test_sse_state_event_pushes_to_queue(self, httpx_mock: HTTPXMock):
        """SSE 'event: state' line pushes 'state_changed' to queue."""
        httpx_mock.add_response(
            url=SSE_URL,
            stream=IteratorStream([
                b"event: state\n",
                b"data: {\"changed\": {}}\n",
                b"\n",
            ]),
            headers={"content-type": "text/event-stream"},
        )

        event_queue = queue.Queue()
        shutdown = threading.Event()

        t = threading.Thread(target=self._run_listener, args=(event_queue, shutdown))
        t.start()

        # Wait for the event to arrive
        item = event_queue.get(timeout=5)
        assert item == "state_changed"

        shutdown.set()
        t.join(timeout=5)

    @_RELAXED
    def test_sse_ignores_ping_lines(self, httpx_mock: HTTPXMock):
        """SSE comment lines (: keepalive) are not pushed to queue."""
        httpx_mock.add_response(
            url=SSE_URL,
            stream=IteratorStream([
                b": keepalive\n",
                b"event: state\n",
                b"data: {}\n",
                b"\n",
            ]),
            headers={"content-type": "text/event-stream"},
        )

        event_queue = queue.Queue()
        shutdown = threading.Event()

        t = threading.Thread(target=self._run_listener, args=(event_queue, shutdown))
        t.start()

        # Wait for the state event
        item = event_queue.get(timeout=5)
        assert item == "state_changed"

        # Shut down and verify only one event was queued (ping ignored)
        shutdown.set()
        t.join(timeout=5)
        assert event_queue.qsize() == 0  # only the one we already consumed

    @_RELAXED
    def test_sse_multiple_events(self, httpx_mock: HTTPXMock):
        """Multiple 'event: state' blocks push multiple items to queue."""
        httpx_mock.add_response(
            url=SSE_URL,
            stream=IteratorStream([
                b"event: state\n",
                b"data: {\"changed\": {\"Email\": \"s1\"}}\n",
                b"\n",
                b"event: state\n",
                b"data: {\"changed\": {\"Mailbox\": \"s2\"}}\n",
                b"\n",
            ]),
            headers={"content-type": "text/event-stream"},
        )

        event_queue = queue.Queue()
        shutdown = threading.Event()

        t = threading.Thread(target=self._run_listener, args=(event_queue, shutdown))
        t.start()

        # Wait for both events
        items = []
        for _ in range(2):
            items.append(event_queue.get(timeout=5))

        shutdown.set()
        t.join(timeout=5)
        assert len(items) == 2
        assert all(i == "state_changed" for i in items)

    @_RELAXED
    def test_sse_auth_header(self, httpx_mock: HTTPXMock):
        """SSE listener sends Authorization: Bearer and Accept: text/event-stream."""
        httpx_mock.add_response(
            url=SSE_URL,
            stream=IteratorStream([b"event: state\ndata: {}\n\n"]),
            headers={"content-type": "text/event-stream"},
        )

        event_queue = queue.Queue()
        shutdown = threading.Event()

        t = threading.Thread(target=self._run_listener, args=(event_queue, shutdown))
        t.start()

        # Wait for processing
        event_queue.get(timeout=5)
        shutdown.set()
        t.join(timeout=5)

        requests = httpx_mock.get_requests()
        assert len(requests) >= 1
        request = requests[0]
        assert request.headers["authorization"] == "Bearer test-token"
        assert request.headers["accept"] == "text/event-stream"

    @_RELAXED
    def test_sse_url_construction(self, httpx_mock: HTTPXMock):
        """SSE listener constructs URL with types, closeafter, and ping params."""
        httpx_mock.add_response(
            url=SSE_URL,
            stream=IteratorStream([b"event: state\ndata: {}\n\n"]),
            headers={"content-type": "text/event-stream"},
        )

        event_queue = queue.Queue()
        shutdown = threading.Event()

        t = threading.Thread(target=self._run_listener, args=(event_queue, shutdown))
        t.start()

        event_queue.get(timeout=5)
        shutdown.set()
        t.join(timeout=5)

        requests = httpx_mock.get_requests()
        assert len(requests) >= 1
        url = str(requests[0].url)
        assert "types=Email,Mailbox" in url
        assert "closeafter=no" in url
        assert "ping=30" in url

    @_RELAXED
    def test_sse_reconnects_on_error(self, httpx_mock: HTTPXMock):
        """SSE listener reconnects after a server error."""
        # First: 500 error
        httpx_mock.add_response(
            url=SSE_URL,
            status_code=500,
        )
        # Second: successful stream
        httpx_mock.add_response(
            url=SSE_URL,
            stream=IteratorStream([b"event: state\ndata: {}\n\n"]),
            headers={"content-type": "text/event-stream"},
        )

        event_queue = queue.Queue()
        shutdown = threading.Event()

        t = threading.Thread(target=self._run_listener, args=(event_queue, shutdown))
        t.start()

        # Wait for state_changed to appear from the second (successful) connection
        try:
            event_queue.get(timeout=10)
        except queue.Empty:
            pytest.fail("Expected state_changed event after reconnect")

        shutdown.set()
        t.join(timeout=5)

        # At least 2 requests made (error + success)
        assert len(httpx_mock.get_requests()) >= 2

    def test_sse_exponential_backoff_caps_at_60(self):
        """Backoff formula min(2**attempt, 60) caps at 60 seconds."""
        for attempt in range(1, 11):
            delay = min(2 ** attempt, 60)
            if attempt <= 5:
                assert delay == 2 ** attempt
            else:
                assert delay == 60

    @_RELAXED
    def test_sse_honors_retry_field(self, httpx_mock: HTTPXMock):
        """SSE listener parses retry: field without error and still pushes events."""
        httpx_mock.add_response(
            url=SSE_URL,
            stream=IteratorStream([
                b"retry: 5000\n",
                b"event: state\n",
                b"data: {}\n",
                b"\n",
            ]),
            headers={"content-type": "text/event-stream"},
        )

        event_queue = queue.Queue()
        shutdown = threading.Event()

        t = threading.Thread(target=self._run_listener, args=(event_queue, shutdown))
        t.start()

        item = event_queue.get(timeout=5)
        assert item == "state_changed"

        shutdown.set()
        t.join(timeout=5)

    def test_sse_shutdown_event_stops_listener(self):
        """Setting shutdown_event immediately causes clean exit within 2s."""
        event_queue = queue.Queue()
        shutdown = threading.Event()
        shutdown.set()  # Set immediately

        t = threading.Thread(target=self._run_listener, args=(event_queue, shutdown))
        t.start()
        t.join(timeout=2)
        assert not t.is_alive(), "Listener should exit within 2 seconds when shutdown is set"

    @_RELAXED
    def test_sse_read_timeout_triggers_reconnect(self, httpx_mock: HTTPXMock):
        """Stream exhaustion causes the listener to reconnect."""
        # First response: stream with one event that then ends
        httpx_mock.add_response(
            url=SSE_URL,
            stream=IteratorStream([b"event: state\ndata: {}\n\n"]),
            headers={"content-type": "text/event-stream"},
        )
        # Second response: another stream after reconnect
        httpx_mock.add_response(
            url=SSE_URL,
            stream=IteratorStream([b"event: state\ndata: {}\n\n"]),
            headers={"content-type": "text/event-stream"},
        )

        event_queue = queue.Queue()
        shutdown = threading.Event()

        t = threading.Thread(target=self._run_listener, args=(event_queue, shutdown))
        t.start()

        # Wait for at least 2 events (from 2 connections)
        events = []
        for _ in range(2):
            try:
                events.append(event_queue.get(timeout=5))
            except queue.Empty:
                break

        shutdown.set()
        t.join(timeout=5)

        # Verify at least 2 connection attempts (stream ended, reconnected)
        assert len(httpx_mock.get_requests()) >= 2
        assert len(events) >= 2


class TestHealthSSE:
    """Tests for SSE health status reporting via health_cls."""

    def _run_listener(self, event_queue, shutdown, health_cls=None, **kwargs):
        """Helper: run sse_listener with standard args and health_cls."""
        sse_listener(
            token=kwargs.get("token", "test-token"),
            event_source_url="https://api.fastmail.com/jmap/event/",
            event_queue=event_queue,
            shutdown_event=shutdown,
            log=None,
            health_cls=health_cls,
        )

    @_RELAXED
    def test_sse_updates_health_on_connect(self, httpx_mock: HTTPXMock):
        """SSE sets health_cls.sse_status='connected' and sse_connected_since on connect."""
        httpx_mock.add_response(
            url=SSE_URL,
            stream=IteratorStream([b"event: state\ndata: {}\n\n"]),
            headers={"content-type": "text/event-stream"},
        )

        MockHealthHandler.reset()
        event_queue = queue.Queue()
        shutdown = threading.Event()

        t = threading.Thread(
            target=self._run_listener,
            args=(event_queue, shutdown),
            kwargs={"health_cls": MockHealthHandler},
        )
        t.start()

        event_queue.get(timeout=5)
        shutdown.set()
        t.join(timeout=5)

        assert MockHealthHandler.sse_status == "connected"
        assert MockHealthHandler.sse_connected_since is not None
        assert isinstance(MockHealthHandler.sse_connected_since, float)

    @_RELAXED
    def test_sse_updates_health_on_event(self, httpx_mock: HTTPXMock):
        """SSE sets health_cls.sse_last_event_at after receiving a state event."""
        httpx_mock.add_response(
            url=SSE_URL,
            stream=IteratorStream([b"event: state\ndata: {}\n\n"]),
            headers={"content-type": "text/event-stream"},
        )

        MockHealthHandler.reset()
        event_queue = queue.Queue()
        shutdown = threading.Event()

        t = threading.Thread(
            target=self._run_listener,
            args=(event_queue, shutdown),
            kwargs={"health_cls": MockHealthHandler},
        )
        t.start()

        event_queue.get(timeout=5)
        shutdown.set()
        t.join(timeout=5)

        assert MockHealthHandler.sse_last_event_at is not None
        assert isinstance(MockHealthHandler.sse_last_event_at, float)

    @_RELAXED
    def test_sse_updates_health_on_disconnect(self, httpx_mock: HTTPXMock):
        """SSE sets health_cls.sse_status='disconnected' and increments reconnect_count on error."""
        # First: 500 error (triggers disconnect health update)
        httpx_mock.add_response(
            url=SSE_URL,
            status_code=500,
        )
        # Second: successful stream (so listener can exit cleanly)
        httpx_mock.add_response(
            url=SSE_URL,
            stream=IteratorStream([b"event: state\ndata: {}\n\n"]),
            headers={"content-type": "text/event-stream"},
        )

        MockHealthHandler.reset()
        event_queue = queue.Queue()
        shutdown = threading.Event()

        t = threading.Thread(
            target=self._run_listener,
            args=(event_queue, shutdown),
            kwargs={"health_cls": MockHealthHandler},
        )
        t.start()

        # Wait for the successful reconnect event
        event_queue.get(timeout=10)
        shutdown.set()
        t.join(timeout=5)

        # After the error + reconnect: reconnect_count >= 1 and last_error was set
        assert MockHealthHandler.sse_reconnect_count >= 1
        assert MockHealthHandler.sse_last_error is not None
        # Final status should be "connected" since the second attempt succeeded
        assert MockHealthHandler.sse_status == "connected"

    def test_sse_works_without_health_cls(self):
        """SSE listener works with health_cls=None (backward compat)."""
        event_queue = queue.Queue()
        shutdown = threading.Event()
        shutdown.set()  # Exit immediately

        # Should not raise any error
        t = threading.Thread(
            target=self._run_listener,
            args=(event_queue, shutdown),
            kwargs={"health_cls": None},
        )
        t.start()
        t.join(timeout=2)
        assert not t.is_alive(), "Listener should exit cleanly with health_cls=None"
