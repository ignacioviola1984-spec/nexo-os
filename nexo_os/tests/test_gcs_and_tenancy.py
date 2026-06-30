"""GCS backend fails closed without config; per-tenant isolation resolves to
separate stores/datasets/prefixes while leaving the default tenant unchanged."""

from __future__ import annotations

import pytest

from nexo_os.data.repository import DataSourceUnavailable


def test_gcs_fails_closed_without_bucket(monkeypatch) -> None:
    from nexo_os.config import get_settings
    from nexo_os.data.factory import get_repository

    get_settings.cache_clear()
    monkeypatch.setenv("NEXO_DATA_SOURCE", "gcs")
    monkeypatch.delenv("NEXO_GCS_BUCKET", raising=False)
    try:
        with pytest.raises(DataSourceUnavailable, match="NEXO_GCS_BUCKET"):
            get_repository()
    finally:
        get_settings.cache_clear()


def test_gcs_fails_closed_without_library(monkeypatch) -> None:
    """With a bucket set but google-cloud-storage not installed, the backend must
    fail closed (never stub a client)."""
    from nexo_os.config import get_settings
    from nexo_os.data.factory import get_repository

    get_settings.cache_clear()
    monkeypatch.setenv("NEXO_DATA_SOURCE", "gcs")
    monkeypatch.setenv("NEXO_GCS_BUCKET", "some-bucket")
    try:
        with pytest.raises(DataSourceUnavailable, match="google-cloud-storage"):
            get_repository()
    finally:
        get_settings.cache_clear()


def test_tenant_synthetic_paths_isolated() -> None:
    from nexo_os.config import get_settings
    from nexo_os.data.factory import DEFAULT_TENANT, tenant_synthetic_paths

    s = get_settings()
    # Default tenant keeps the original paths (backward compatible).
    assert tenant_synthetic_paths(s, DEFAULT_TENANT) == (s.synthetic_db_path, s.runtime_db_path)
    # Distinct tenants get distinct, isolated stores.
    acme_syn, acme_rt = tenant_synthetic_paths(s, "acme")
    beta_syn, beta_rt = tenant_synthetic_paths(s, "beta")
    assert acme_syn != s.synthetic_db_path
    assert "acme" in acme_syn.as_posix() and "acme" in acme_rt.as_posix()
    assert acme_syn != beta_syn and acme_rt != beta_rt


def test_tenant_dataset_and_prefix_scoping() -> None:
    from nexo_os.config import get_settings
    from nexo_os.data.factory import DEFAULT_TENANT, tenant_bq_dataset, tenant_gcs_prefix

    s = get_settings()
    assert tenant_bq_dataset(s, DEFAULT_TENANT) == s.bq_dataset
    assert tenant_bq_dataset(s, "acme") == f"{s.bq_dataset}_acme"
    assert tenant_gcs_prefix(s, DEFAULT_TENANT) == s.gcs_prefix
    assert "acme" in tenant_gcs_prefix(s, "acme")


def test_factory_honors_tenant_id_setting(tmp_path, monkeypatch) -> None:
    """NEXO_TENANT_ID scopes the synthetic store; a missing tenant store fails closed
    at the tenant-scoped path (proving the tenant branch was taken)."""
    from nexo_os.config import get_settings
    from nexo_os.data.factory import get_repository

    get_settings.cache_clear()
    monkeypatch.setenv("NEXO_TENANT_ID", "acme")
    monkeypatch.setenv("NEXO_SYNTHETIC_DB_PATH", str(tmp_path / "nexo.duckdb"))
    try:
        with pytest.raises(DataSourceUnavailable, match="tenants"):
            get_repository()
    finally:
        get_settings.cache_clear()
