"""Single clock. System timestamps are naive UTC so they round-trip cleanly through
DuckDB TIMESTAMP and keep the audit hash chain reproducible across read/write."""

from __future__ import annotations

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
