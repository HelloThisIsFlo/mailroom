"""Tests for the structured logging module."""

import json
import sys
from io import StringIO
from unittest.mock import patch

import structlog

from mailroom.core.logging import configure_logging, get_logger


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
