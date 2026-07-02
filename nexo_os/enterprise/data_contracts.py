"""Data contracts for ingestion from real ERP / AMS (agency-management) systems.

``bq_validate`` checks that a live BigQuery dataset's *columns and types* match the
canonical schema. A data contract goes further: it is the agreement the upstream system
must honor for the extract to be trusted - required columns, no-nulls on keys, a unique
primary key, a minimum row count, and a freshness SLA on the snapshot. Contracts are
derived from the canonical schema (``schema_def``) so they can never drift from it.

Validation runs against a pandas DataFrame (what the domain stores already produce), so
the same check works for a BigQuery extract, a GCS Parquet drop, a Turso table, or the
synthetic store - fail closed on any violation before the data reaches the agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from nexo_os.config import Settings, get_settings
from nexo_os.data.schema_def import DOMAIN_TABLES, Table


@dataclass(frozen=True)
class DataContract:
    table: str
    required_columns: tuple[str, ...]
    not_null_columns: tuple[str, ...]
    unique_key: tuple[str, ...]
    pii_columns: tuple[str, ...]
    min_rows: int = 1
    # Freshness is opt-in per contract: it only makes sense on a column whose newest
    # value is expected to track the snapshot (an event/movement date), never on a
    # historical field like a client's onboarding date. Left unset by default so the
    # structural contract (columns, not-null, unique key, row count) never produces a
    # false "stale" failure on legitimately historical rows.
    freshness_column: str | None = None
    freshness_sla_hours: int | None = None

    @classmethod
    def from_table(
        cls,
        table: Table,
        *,
        freshness_column: str | None = None,
        freshness_sla_hours: int | None = None,
    ) -> DataContract:
        cols = [c.name for c in table.columns]
        pk = tuple(c.name for c in table.columns if c.pk)
        not_null = tuple(c.name for c in table.columns if not c.nullable)
        if freshness_column and freshness_column not in cols:
            raise ValueError(f"{table.name}: freshness column '{freshness_column}' not in schema")
        return cls(
            table=table.name,
            required_columns=tuple(cols),
            not_null_columns=not_null,
            unique_key=pk,
            pii_columns=tuple(table.pii_columns),
            min_rows=1,
            freshness_column=freshness_column,
            freshness_sla_hours=freshness_sla_hours if freshness_column else None,
        )


@dataclass(frozen=True)
class ContractResult:
    table: str
    ok: bool
    rows: int
    violations: list[str] = field(default_factory=list)


def domain_contracts(settings: Settings | None = None) -> list[DataContract]:
    """The structural contract set for every canonical domain table (columns, not-null,
    unique key, min rows). Freshness is opt-in per deployment via
    ``with_freshness`` — the newest interaction, for instance, should track the snapshot
    once the extract is live, but that SLA is a deployment decision, not a schema fact."""
    settings = settings or get_settings()  # noqa: F841 - kept for signature stability
    return [DataContract.from_table(t) for t in DOMAIN_TABLES]


def with_freshness(contract: DataContract, freshness_column: str, sla_hours: int) -> DataContract:
    """Return a copy of ``contract`` with a freshness SLA on ``freshness_column``."""
    from dataclasses import replace

    if freshness_column not in contract.required_columns:
        raise ValueError(f"{contract.table}: '{freshness_column}' not in contract columns")
    return replace(contract, freshness_column=freshness_column, freshness_sla_hours=sla_hours)


def _freshness_age_hours(series: pd.Series, as_of: datetime) -> float | None:
    """Most-recent value in a date/period column, as hours before ``as_of``. Handles
    ISO date strings, ``date``/``datetime``, and ``YYYY-MM`` period strings."""
    values = series.dropna()
    if values.empty:
        return None
    parsed: list[datetime] = []
    for v in values:
        try:
            if isinstance(v, datetime):
                parsed.append(v)
            elif isinstance(v, date):
                parsed.append(datetime(v.year, v.month, v.day))
            else:
                s = str(v)
                if len(s) == 7 and s[4] == "-":  # YYYY-MM period -> first of month
                    s = s + "-01"
                parsed.append(datetime.fromisoformat(s[:19].replace("Z", "")))
        except (ValueError, TypeError):
            continue
    if not parsed:
        return None
    newest = max(parsed)
    return (as_of - newest).total_seconds() / 3600.0


def evaluate_dataframe(
    contract: DataContract, df: pd.DataFrame, as_of: datetime | None = None
) -> ContractResult:
    """Check a DataFrame against a contract. Deterministic; returns every violation."""
    violations: list[str] = []
    cols = set(df.columns)

    missing = [c for c in contract.required_columns if c not in cols]
    if missing:
        violations.append(f"missing columns: {', '.join(missing)}")

    if len(df) < contract.min_rows:
        violations.append(f"row count {len(df)} < min {contract.min_rows}")

    for c in contract.not_null_columns:
        if c in cols and df[c].isna().any():
            n = int(df[c].isna().sum())
            violations.append(f"column '{c}' has {n} null(s) (not-null)")

    if contract.unique_key and all(c in cols for c in contract.unique_key):
        dupes = int(df.duplicated(subset=list(contract.unique_key)).sum())
        if dupes:
            violations.append(f"unique key {contract.unique_key} has {dupes} duplicate row(s)")

    if (
        contract.freshness_column
        and contract.freshness_sla_hours
        and contract.freshness_column in cols
    ):
        ref = as_of or datetime.now()  # noqa: DTZ005 - naive compare vs naive stored dates
        age = _freshness_age_hours(df[contract.freshness_column], ref)
        if age is not None and age > contract.freshness_sla_hours:
            violations.append(
                f"stale: newest '{contract.freshness_column}' is {age:.0f}h old "
                f"(SLA {contract.freshness_sla_hours}h)"
            )

    return ContractResult(
        table=contract.table, ok=not violations, rows=len(df), violations=violations
    )


def validate_source(
    reader,
    contracts: list[DataContract] | None = None,
    as_of: datetime | None = None,
) -> list[ContractResult]:
    """Run every contract using ``reader(table_name) -> DataFrame``. A reader that
    raises for a table is reported as a hard violation (fail closed)."""
    contracts = contracts or domain_contracts()
    results: list[ContractResult] = []
    for contract in contracts:
        try:
            df = reader(contract.table)
        except Exception as exc:
            results.append(
                ContractResult(contract.table, ok=False, rows=0, violations=[f"unreadable: {exc}"])
            )
            continue
        results.append(evaluate_dataframe(contract, df, as_of))
    return results


def duckdb_reader(db_path):
    """A ``reader`` over a local DuckDB store (synthetic / GCS-loaded)."""
    import duckdb

    def read(table: str) -> pd.DataFrame:
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            return con.execute(f"SELECT * FROM {table}").df()  # noqa: S608 - table from schema
        finally:
            con.close()

    return read
