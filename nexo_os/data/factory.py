"""The single factory that selects the repository backend. Nothing else in the
codebase knows which backend is live — agents and core depend only on the
NexoRepository interface.
"""

from __future__ import annotations

from datetime import date

from nexo_os.config import DataSource, get_settings
from nexo_os.data.repository import NexoRepository


def get_repository(snapshot_fecha: date | None = None) -> NexoRepository:
    """Return the configured repository. Defaults to synthetic; BigQuery fails closed
    if selected without project/credentials."""
    settings = get_settings()
    if settings.data_source is DataSource.bigquery:
        from nexo_os.data.bigquery import BigQueryRepository

        return BigQueryRepository(snapshot_fecha=snapshot_fecha)

    from nexo_os.data.synthetic import SyntheticRepository

    return SyntheticRepository(snapshot_fecha=snapshot_fecha)
