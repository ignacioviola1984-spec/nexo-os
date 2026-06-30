# Turso / libSQL backend

Turso is an optional, opt-in backend (hosted libSQL, SQLite-compatible) alongside
synthetic (default) and BigQuery. Like BigQuery it **fails closed** until configured:
selecting it without a database URL raises `DataSourceUnavailable` rather than
fabricating data. Switching to it is **config — no change to agent or core code**.

Two ways to use it:

1. **Full backend** (`NEXO_DATA_SOURCE=turso`): Turso serves both the domain tables
   and the system tables — the hosted parallel to BigQuery.
2. **Hybrid system store** (`NEXO_SYSTEM_STORE=turso`): domain reads stay on
   synthetic/BigQuery, but the system tables (`acciones`, `agent_runs`, `audit_log`)
   are read/written in Turso. This persists approvals and the hash-chained audit log
   across a Streamlit Cloud restart, whose ephemeral filesystem would otherwise wipe
   the local runtime store.

## Money is exact (the one thing to know)

SQLite/libSQL has no exact NUMERIC type — its REAL affinity is IEEE float and would
corrupt ARS amounts. So `MONEY`/`PCT` columns are **TEXT**: the `Decimal` is stored as
its string form and coerced back to `Decimal` by the pydantic models on read. Dates
and timestamps are ISO **TEXT** (which sort chronologically); booleans are `INTEGER`
0/1. All monetary math happens in `nexo_os.core`; SQL never compares money or dates
numerically. The mapping lives in `nexo_os/data/schema_def.py` (the third element of
each type tuple) and is guarded by `test_schema_contract.py`.

## Install

```bash
pip install -e ".[turso]"   # pulls the pure-Python libsql-client (no native build)
```

## Local file (dev / CI — no account needed)

libSQL's `file:` URL scheme is a local SQLite database, so the whole backend runs with
zero network/secrets. Useful for development and tests.

```
NEXO_TURSO_DATABASE_URL=file:./nexo_turso.db
NEXO_DATA_SOURCE=turso
```

```bash
python -m nexo_os seed         # produces the ground-truth files (DuckDB)
python -m nexo_os turso-seed   # loads the synthetic dataset into Turso
python -m nexo_os eval         # all 7 suites must pass against Turso
```

## Remote Turso (hosted)

1. Create a database and an auth token (Turso dashboard or `turso db create` /
   `turso db tokens create`).
2. Configure `.env`:
   ```
   NEXO_TURSO_DATABASE_URL=libsql://<db>.turso.io
   NEXO_TURSO_AUTH_TOKEN=<token>     # gitignored
   ```
3. Seed and smoke-test:
   ```bash
   python -m nexo_os seed && python -m nexo_os turso-seed
   NEXO_DATA_SOURCE=turso python -m nexo_os orchestrate
   ```

### Hybrid (domain stays synthetic/BigQuery)

```
NEXO_DATA_SOURCE=synthetic
NEXO_SYSTEM_STORE=turso
NEXO_TURSO_DATABASE_URL=libsql://<db>.turso.io
NEXO_TURSO_AUTH_TOKEN=<token>
```
`get_repository()` returns a `CompositeRepository` (`data_source = "synthetic+turso"`):
domain reads from synthetic, system tables in Turso. No `turso-seed` needed — system
tables are created on first connect.

## Notes
- `turso-seed` drops and recreates the **domain** tables for a clean reload; it leaves
  the system tables intact so re-seeding never wipes approvals or the audit log.
- The eval's numbers/detection suites are calibrated to the synthetic dataset; point
  them at a Turso copy of that dataset (what `turso-seed` produces) when used as a gate.
- Make `audit_log` append-only at the database level where the platform allows it (see
  SECURITY.md) — the hash chain is tamper-evidence, not prevention.
- The sync libSQL client runs a worker thread; the CLI closes it on exit
  (`turso.close_all()`), and long-lived hosts (Streamlit) keep one cached client.
