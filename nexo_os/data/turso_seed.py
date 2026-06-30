"""Seed a Turso/libSQL database with the synthetic dataset.

Reuses the deterministic generator (the same rows that back the DuckDB synthetic
store and the ground-truth files), creates the canonical schema in Turso, and loads
the domain tables. System tables (acciones, agent_runs, audit_log) are created empty
and filled at runtime by the orchestrator. Idempotent: domain tables are dropped and
recreated so re-seeding is safe.

Run via `nexo turso-seed` (see cli.py). The ground-truth JSON/MD are produced by the
regular `nexo seed`; this command does not touch them.
"""

from __future__ import annotations

from nexo_os.config import get_settings
from nexo_os.data.generate import _row_to_tuple, generate
from nexo_os.data.repository import DataSourceUnavailable
from nexo_os.data.schema_def import ALL_TABLES, DOMAIN_TABLES, TABLES_BY_NAME
from nexo_os.data.turso import _ddl_statements, _param
from nexo_os.logging_setup import configure_logging, get_logger

log = get_logger("turso_seed")


def seed_turso(database_url: str | None = None, auth_token: str | None = None) -> dict:
    """Generate the synthetic dataset and load it into Turso. Returns row counts."""
    configure_logging()
    settings = get_settings()
    url = database_url or settings.turso_database_url
    token = auth_token or settings.turso_auth_token
    if not url:
        raise DataSourceUnavailable(
            "Cannot seed Turso: NEXO_TURSO_DATABASE_URL is not set. Failing closed."
        )
    try:
        import libsql_client
    except ImportError as exc:  # pragma: no cover - import guard
        raise DataSourceUnavailable(
            'Turso seed requires libsql-client. Install with: pip install -e ".[turso]".'
        ) from exc

    b = generate(settings.synthetic_seed, settings.synthetic_snapshot_fecha)

    kwargs: dict[str, object] = {"url": url}
    if token:
        kwargs["auth_token"] = token
    client = libsql_client.create_client_sync(**kwargs)
    try:
        # Recreate the full schema (domain dropped for a clean reload; system tables
        # are left intact so re-seeding never wipes approvals or the audit log).
        for t in DOMAIN_TABLES:
            client.execute(f"DROP TABLE IF EXISTS {t.name}")
        for stmt in _ddl_statements(ALL_TABLES):
            client.execute(stmt)

        counts: dict[str, int] = {}
        for t in DOMAIN_TABLES:
            rows = b.tables[t.name]
            counts[t.name] = len(rows)
            if not rows:
                continue
            cols = [c.name for c in TABLES_BY_NAME[t.name].columns]
            placeholders = ", ".join("?" for _ in cols)
            sql = f"INSERT INTO {t.name} ({', '.join(cols)}) VALUES ({placeholders})"
            client.batch([(sql, [_param(v) for v in _row_to_tuple(t.name, r)]) for r in rows])
    finally:
        client.close()

    log.info("turso_seed.complete", counts=counts, store=url)
    return counts
