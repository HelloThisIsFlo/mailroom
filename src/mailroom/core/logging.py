"""Structured logging configuration for mailroom.

Production (non-TTY stderr): structured JSON with ISO timestamps.
Development (TTY stderr): colored console output for readability.
"""

import logging
import sys

import structlog


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
