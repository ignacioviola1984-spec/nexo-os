"""Regenerate the canonical BigQuery and SQLite/libSQL DDL from schema_def.py.

Usage: python scripts/render_ddl.py
"""

from __future__ import annotations

from pathlib import Path

from nexo_os.data.schema_def import render_bigquery_ddl, render_sqlite_ddl

BQ_HEADER = (
    "-- Canonical BigQuery DDL for the Nexo data model. GENERATED from "
    "nexo_os/data/schema_def.py.\n"
    "-- Do not edit by hand: edit schema_def.py and re-run scripts/render_ddl.py.\n"
    "-- Replace the unqualified names with project.dataset-qualified names at deploy time.\n\n"
)

SQLITE_HEADER = (
    "-- Canonical SQLite/libSQL DDL for the Nexo Turso backend. GENERATED from "
    "nexo_os/data/schema_def.py.\n"
    "-- Do not edit by hand: edit schema_def.py and re-run scripts/render_ddl.py.\n"
    "-- Money (MONEY/PCT) is TEXT (Decimal as string); dates/timestamps are ISO TEXT;\n"
    "-- booleans are INTEGER 0/1. The Turso backend creates tables from this contract.\n\n"
)


def main() -> None:
    schema_dir = Path(__file__).resolve().parent.parent / "nexo_os" / "data" / "schema"
    bq = schema_dir / "ddl_bigquery.sql"
    bq.write_text(BQ_HEADER + render_bigquery_ddl(), encoding="utf-8")
    print(f"wrote {bq}")
    sqlite = schema_dir / "ddl_sqlite.sql"
    sqlite.write_text(SQLITE_HEADER + render_sqlite_ddl(), encoding="utf-8")
    print(f"wrote {sqlite}")


if __name__ == "__main__":
    main()
