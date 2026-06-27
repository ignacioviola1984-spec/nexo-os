"""Contract tests: the pydantic models match the canonical schema column-for-column,
the PII registry is wired, and both DDL dialects render for every table."""

from __future__ import annotations

from nexo_os.data.models import MODEL_TABLE
from nexo_os.data.schema_def import (
    ALL_TABLES,
    PII_FIELDS,
    TABLES_BY_NAME,
    render_bigquery_ddl,
    render_duckdb_ddl,
)


def test_models_match_schema_columns() -> None:
    for model, table_name in MODEL_TABLE.items():
        schema_cols = [c.name for c in TABLES_BY_NAME[table_name].columns]
        model_cols = list(model.model_fields)
        assert model_cols == schema_cols, f"{table_name}: model/schema column mismatch"


def test_every_table_has_a_model() -> None:
    modeled = set(MODEL_TABLE.values())
    assert modeled == set(TABLES_BY_NAME), "every canonical table must have a model"


def test_every_table_has_a_primary_key() -> None:
    for t in ALL_TABLES:
        assert any(c.pk for c in t.columns), f"{t.name} has no primary key"


def test_pii_registry_flags_known_fields() -> None:
    assert "documento" in PII_FIELDS["clientes"]
    assert "email" in PII_FIELDS["clientes"]
    assert "nombre" in PII_FIELDS["clientes"]
    assert "nombre_prospecto" in PII_FIELDS["leads"]
    # system + reference tables carry no PII
    assert PII_FIELDS["acciones"] == set()
    assert PII_FIELDS["aseguradoras"] == set()


def test_ddl_renders_for_all_tables() -> None:
    bq = render_bigquery_ddl()
    duck = render_duckdb_ddl()
    for t in ALL_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {t.name}" in bq
        assert f"CREATE TABLE IF NOT EXISTS {t.name}" in duck
    # money uses NUMERIC in BQ and DECIMAL in DuckDB, never float
    assert "prima_ars NUMERIC" in bq
    assert "prima_ars DECIMAL(20, 2)" in duck
