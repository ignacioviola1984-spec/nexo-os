"""Regenerate the canonical BigQuery DDL from schema_def.py.

Usage: python scripts/render_ddl.py
"""

from __future__ import annotations

from pathlib import Path

from nexo_os.data.schema_def import render_bigquery_ddl

HEADER = (
    "-- Canonical BigQuery DDL for the Nexo data model. GENERATED from "
    "nexo_os/data/schema_def.py.\n"
    "-- Do not edit by hand: edit schema_def.py and re-run scripts/render_ddl.py.\n"
    "-- Replace the unqualified names with project.dataset-qualified names at deploy time.\n\n"
)


def main() -> None:
    out = (
        Path(__file__).resolve().parent.parent / "nexo_os" / "data" / "schema" / "ddl_bigquery.sql"
    )
    out.write_text(HEADER + render_bigquery_ddl(), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
