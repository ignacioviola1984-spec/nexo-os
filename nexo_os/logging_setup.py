"""Structured (JSON) logging. Every record carries a run_id when one is bound.
No PII in log bodies — log identifiers, never names/documents/contacts.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog to emit JSON lines to stderr. Idempotent."""
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level) if isinstance(level, str) else level
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def bind_run_id(run_id: str) -> None:
    """Bind a run_id to the context so all subsequent log records carry it."""
    structlog.contextvars.bind_contextvars(run_id=run_id)


def clear_run_context() -> None:
    structlog.contextvars.clear_contextvars()
