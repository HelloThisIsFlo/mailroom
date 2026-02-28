"""Tests for the structured logging module."""

import json
import sys
from io import StringIO
from unittest.mock import patch

import structlog

from mailroom.core.logging import configure_logging, get_logger, reorder_keys


def _setup_json_logging(buf: StringIO, level: str = "info") -> None:
    """Configure structlog for JSON output writing to the given buffer.

    Patches sys.stderr so PrintLoggerFactory writes to buf, and
    patches isatty to return False so we get JSON output.
    """
    # configure_logging reads sys.stderr at call time for both
    # the isatty check and the PrintLoggerFactory file argument
    configure_logging(level)


def test_json_output():
    """In non-TTY mode, log output is valid JSON with required fields."""
    buf = StringIO()
    buf.isatty = lambda: False  # type: ignore[attr-defined]

    with patch.object(sys, "stderr", buf):
        configure_logging("info")
        log = structlog.get_logger()
        log.info("test_event", action="verify", status="ok")

    output = buf.getvalue().strip()
    data = json.loads(output)

    assert data["event"] == "test_event"
    assert data["level"] == "info"
    assert "timestamp" in data
    assert data["action"] == "verify"
    assert data["status"] == "ok"


def test_log_level_filtering():
    """DEBUG messages are hidden at INFO level; INFO messages appear."""
    buf = StringIO()
    buf.isatty = lambda: False  # type: ignore[attr-defined]

    with patch.object(sys, "stderr", buf):
        configure_logging("info")
        log = structlog.get_logger()
        log.debug("should_be_hidden")
        log.info("should_appear")

    output = buf.getvalue().strip()
    lines = [line for line in output.splitlines() if line.strip()]

    # Only 1 line -- the info message
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["event"] == "should_appear"
    assert data["level"] == "info"


def test_bound_context():
    """Bound context fields appear in JSON output."""
    buf = StringIO()
    buf.isatty = lambda: False  # type: ignore[attr-defined]

    with patch.object(sys, "stderr", buf):
        configure_logging("info")
        log = structlog.get_logger()
        bound = log.bind(action="sweep", sender="test@example.com")
        bound.info("processing")

    output = buf.getvalue().strip()
    data = json.loads(output)

    assert data["event"] == "processing"
    assert data["action"] == "sweep"
    assert data["sender"] == "test@example.com"


def test_error_logging_with_exception():
    """Exceptions are serialized as structured fields in JSON output."""
    buf = StringIO()
    buf.isatty = lambda: False  # type: ignore[attr-defined]

    with patch.object(sys, "stderr", buf):
        configure_logging("info")
        log = structlog.get_logger()
        try:
            raise ValueError("something went wrong")
        except ValueError:
            log.error("operation_failed", exc_info=True)

    output = buf.getvalue().strip()
    data = json.loads(output)

    assert data["event"] == "operation_failed"
    assert data["level"] == "error"
    # Exception info should be present -- structlog serializes it as 'exception' key
    output_str = json.dumps(data)
    assert "ValueError" in output_str
    assert "something went wrong" in output_str


def test_reorder_keys_processor():
    """reorder_keys places priority fields first and preserves all values."""
    event_dict = {
        "extra": "data",
        "level": "info",
        "event": "something_happened",
        "timestamp": "2026-01-01T00:00:00Z",
        "component": "workflow",
        "detail": "abc",
    }
    result = reorder_keys(None, "info", event_dict)

    keys = list(result.keys())
    assert keys[:4] == ["timestamp", "level", "component", "event"]
    # All original values preserved
    assert result == event_dict


def test_reorder_keys_without_component():
    """reorder_keys works when component is absent."""
    event_dict = {
        "extra": "data",
        "level": "warning",
        "event": "no_component",
        "timestamp": "2026-01-01T00:00:00Z",
    }
    result = reorder_keys(None, "warning", event_dict)

    keys = list(result.keys())
    assert keys[:3] == ["timestamp", "level", "event"]
    assert result == event_dict


def test_json_field_order_with_component():
    """JSON output has fields in order: timestamp, level, component, event, ...rest."""
    buf = StringIO()
    buf.isatty = lambda: False  # type: ignore[attr-defined]

    with patch.object(sys, "stderr", buf):
        configure_logging("info")
        log = structlog.get_logger(component="test")
        log.info("check_order", extra_field="value")

    output = buf.getvalue().strip()
    data = json.loads(output)
    keys = list(data.keys())

    assert keys[:4] == ["timestamp", "level", "component", "event"]
    assert data["extra_field"] == "value"
    assert data["event"] == "check_order"
    assert data["component"] == "test"


def test_json_field_order_without_component():
    """JSON output without component: timestamp, level, event, ...rest."""
    buf = StringIO()
    buf.isatty = lambda: False  # type: ignore[attr-defined]

    with patch.object(sys, "stderr", buf):
        configure_logging("info")
        log = structlog.get_logger()
        log.info("no_component_order", detail="xyz")

    output = buf.getvalue().strip()
    data = json.loads(output)
    keys = list(data.keys())

    assert keys[:3] == ["timestamp", "level", "event"]
    assert data["detail"] == "xyz"


def test_get_logger_convenience():
    """get_logger returns a working structlog logger."""
    buf = StringIO()
    buf.isatty = lambda: False  # type: ignore[attr-defined]

    with patch.object(sys, "stderr", buf):
        configure_logging("info")
        log = get_logger(component="test")
        log.info("hello")

    output = buf.getvalue().strip()
    data = json.loads(output)
    assert data["event"] == "hello"
    assert data["component"] == "test"
