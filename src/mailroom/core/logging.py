"""Structured logging configuration for mailroom.

Production (non-TTY stderr): structured JSON with ISO timestamps.
Development (TTY stderr): colored console output for readability.
"""

import logging
import sys

import structlog


_PRIORITY_KEYS = ("timestamp", "level", "component", "event")


def reorder_keys(
    logger: object, method_name: str, event_dict: dict[str, object]
) -> dict[str, object]:
    """Reorder event_dict so priority fields come first for scannable JSON."""
    ordered: dict[str, object] = {}
    for key in _PRIORITY_KEYS:
        if key in event_dict:
            ordered[key] = event_dict[key]
    for key, value in event_dict.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def configure_logging(log_level: str = "info") -> None:
    """Configure structlog for JSON output (prod) or console (dev).

    Args:
        log_level: Logging level name (debug, info, warning, error, critical).
                   Fed from MAILROOM_LOG_LEVEL config value.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.format_exc_info,
    ]

    if sys.stderr.isatty():
        # Dev: pretty console output
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        # Prod (Docker/k8s): structured JSON
        shared_processors.append(structlog.processors.dict_tracebacks)
        shared_processors.append(reorder_keys)
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )


def get_logger(**initial_context: object) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger, optionally with bound context.

    Convenience wrapper around structlog.get_logger() for discoverability.
    """
    return structlog.get_logger(**initial_context)
