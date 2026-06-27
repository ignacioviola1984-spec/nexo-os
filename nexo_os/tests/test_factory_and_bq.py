"""The factory selects the backend; BigQuery fails closed without configuration."""

from __future__ import annotations

import pytest

from nexo_os.data.repository import DataSourceUnavailable


def test_bigquery_fails_closed_without_project() -> None:
    """With no NEXO_BQ_PROJECT (the default), constructing the BQ backend must raise
    a clear failure — never fabricate or stub a live-looking client."""
    from nexo_os.data.bigquery import BigQueryRepository

    with pytest.raises(DataSourceUnavailable, match="NEXO_BQ_PROJECT"):
        BigQueryRepository()


def test_factory_defaults_to_synthetic_selection(tmp_path, monkeypatch) -> None:
    """Default settings select the synthetic backend (it then fails closed only
    because no store has been seeded yet, proving the synthetic branch was chosen)."""
    from nexo_os.config import get_settings
    from nexo_os.data.factory import get_repository

    get_settings.cache_clear()
    monkeypatch.setenv("NEXO_SYNTHETIC_DB_PATH", str(tmp_path / "absent.duckdb"))
    try:
        with pytest.raises(DataSourceUnavailable, match="Synthetic store not found"):
            get_repository()
    finally:
        get_settings.cache_clear()
