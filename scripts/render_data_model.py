"""Regenerate nexo_os/data/schema/DATA_MODEL.md from schema_def.py.

Usage: python scripts/render_data_model.py
"""

from __future__ import annotations

from pathlib import Path

from nexo_os.data.schema_def import DOMAIN_TABLES, SYSTEM_TABLES, Table

HEADER = """# Nexo canonical data model

This file is the single source of truth a future engineer reads before touching
BigQuery. It is kept in sync with code: the tables below are generated from
`nexo_os/data/schema_def.py`, which also renders the canonical DDL (`ddl_bigquery.sql`,
`ddl_sqlite.sql`) and the DuckDB DDL used by the synthetic store, and drives the
PII redaction registry. **Edit `schema_def.py`, then re-run `scripts/render_ddl.py`
and `scripts/render_data_model.py`.**

## Design rules

- **The schema is the contract.** Synthetic data conforms to it exactly; the future
  BigQuery tables match it (same table names, columns, types, grain).
- **Money is exact.** ARS amounts are `NUMERIC` (BigQuery) / `DECIMAL(20,2)`
  (DuckDB), never float. Commission fractions are `NUMERIC` / `DECIMAL(8,6)` and are
  decimal fractions (`0.15` = 15%). On the Turso/libSQL backend, where SQLite has no
  exact NUMERIC, money is stored as `TEXT` (the Decimal's string form) and parsed back
  to Decimal on read — never `REAL` (see `docs/TURSO.md`).
- **Derived fields are not stored.** `cuotas.dias_mora` and `cuotas.bucket_mora`
  (0 / 1-30 / 31-60 / 61-90 / 90+) are computed at read-time relative to the run
  snapshot date (see `core.morosidad`), so aging never disagrees with the snapshot.
- **PII is flagged** (column `PII` below). The redaction helper uses this registry to
  keep full documents/emails/phones/birth dates away from the model and the logs.

## Entity-relationship overview

```
productores 1--* clientes 1--* polizas 1--* cuotas
                                   |  +--* comisiones *--1 aseguradoras
                                   +--* siniestros
leads 1--* cotizaciones *--1 aseguradoras
leads *--1 productores ;  leads 0..1--1 clientes (set when won)
cotizaciones 0..1--1 polizas (set when bound -> quote-to-bind)
polizas 0..1--1 polizas (poliza_origen_id -> renewal chain)
interacciones *-- (cliente | lead)   [polymorphic via entidad_tipo/entidad_id]
```

## Domain tables
"""


def _esc(text: str) -> str:
    return text.replace("|", "\\|")


def render_table(t: Table) -> str:
    lines = [f"### `{t.name}`", "", f"*Grain: {t.grain}.*", ""]
    if t.notes:
        lines += [f"> {t.notes}", ""]
    lines += [
        "| Column | BQ type | DuckDB type | Null | PII | PK/FK | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in t.columns:
        key = "PK" if c.pk else (f"FK->{c.fk}" if c.fk else "")
        lines.append(
            f"| `{c.name}` | {c.bq_type} | {c.duck_type} | "
            f"{'yes' if c.nullable else ''} | {'PII' if c.pii else ''} | {key} | {_esc(c.note)} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parts = [HEADER]
    for t in DOMAIN_TABLES:
        parts.append(render_table(t))
    parts.append("## System tables (written by Nexo itself)\n")
    parts.append(
        "These are produced by the orchestrator and the HITL inbox. `audit_log` is "
        "append-only and hash-chained (see SECURITY.md).\n"
    )
    for t in SYSTEM_TABLES:
        parts.append(render_table(t))
    out = Path(__file__).resolve().parent.parent / "nexo_os" / "data" / "schema" / "DATA_MODEL.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
