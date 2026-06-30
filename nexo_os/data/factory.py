"""The single factory that selects the repository backend. Nothing else in the
codebase knows which backend is live — agents and core depend only on the
NexoRepository interface.

Multi-tenancy is per-tenant data isolation: the active tenant (NEXO_TENANT_ID, or
the `tenant_id` argument) picks an isolated store / dataset / GCS prefix. The
"default" tenant keeps the original paths, so single-tenant behavior is unchanged.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from nexo_os.config import DataSource, Settings, get_settings
from nexo_os.data.repository import NexoRepository

DEFAULT_TENANT = "default"


def tenant_synthetic_paths(settings: Settings, tenant_id: str) -> tuple[Path, Path]:
    """(synthetic_db_path, runtime_db_path) for a tenant. 'default' = original paths."""
    if tenant_id == DEFAULT_TENANT:
        return settings.synthetic_db_path, settings.runtime_db_path
    syn = settings.synthetic_db_path.parent / "tenants" / tenant_id / "nexo.duckdb"
    rt = settings.runtime_db_path.parent / "tenants" / tenant_id / "nexo.duckdb"
    return syn, rt


def tenant_bq_dataset(settings: Settings, tenant_id: str) -> str:
    """BigQuery dataset for a tenant. 'default' = the configured dataset."""
    if tenant_id == DEFAULT_TENANT:
        return settings.bq_dataset
    return f"{settings.bq_dataset}_{tenant_id}"


def tenant_gcs_prefix(settings: Settings, tenant_id: str) -> str:
    """GCS object prefix for a tenant. 'default' = the configured prefix."""
    if tenant_id == DEFAULT_TENANT:
        return settings.gcs_prefix
    base = settings.gcs_prefix.rstrip("/")
    return f"{base}/tenants/{tenant_id}/"


def get_repository(
    snapshot_fecha: date | None = None, tenant_id: str | None = None
) -> NexoRepository:
    """Return the configured repository for the active tenant. Defaults to
    synthetic; BigQuery/GCS fail closed if selected without project/credentials."""
    settings = get_settings()
    tenant_id = tenant_id or settings.tenant_id

    if settings.data_source is DataSource.bigquery:
        from nexo_os.data.bigquery import BigQueryRepository

        return BigQueryRepository(
            snapshot_fecha=snapshot_fecha, dataset=tenant_bq_dataset(settings, tenant_id)
        )

    if settings.data_source is DataSource.gcs:
        from nexo_os.data.gcs import GcsRepository

        return GcsRepository(
            snapshot_fecha=snapshot_fecha, prefix=tenant_gcs_prefix(settings, tenant_id)
        )

    from nexo_os.data.synthetic import SyntheticRepository

    syn, rt = tenant_synthetic_paths(settings, tenant_id)
    return SyntheticRepository(
        synthetic_db_path=syn, runtime_db_path=rt, snapshot_fecha=snapshot_fecha
    )
