"""The single factory that selects the repository backend. Nothing else in the
codebase knows which backend is live — agents and core depend only on the
NexoRepository interface.
"""

from __future__ import annotations

from datetime import date

from nexo_os.config import DataSource, SystemStore, get_settings
from nexo_os.data.repository import NexoRepository


def _build_domain(data_source: DataSource, snapshot_fecha: date | None) -> NexoRepository:
    """The backend that serves domain reads (and, by default, the system tables too)."""
    if data_source is DataSource.bigquery:
        from nexo_os.data.bigquery import BigQueryRepository

        return BigQueryRepository(snapshot_fecha=snapshot_fecha)
    if data_source is DataSource.turso:
        from nexo_os.data.turso import TursoRepository

        return TursoRepository(snapshot_fecha=snapshot_fecha)

    from nexo_os.data.synthetic import SyntheticRepository

    return SyntheticRepository(snapshot_fecha=snapshot_fecha)


def get_repository(snapshot_fecha: date | None = None) -> NexoRepository:
    """Return the configured repository. Defaults to synthetic; BigQuery and Turso are
    opt-in and fail closed if selected without their connection settings.

    When NEXO_SYSTEM_STORE=turso and the domain source is not already Turso, the
    domain backend is wrapped in a CompositeRepository whose system tables live in
    hosted Turso (the hybrid mode)."""
    settings = get_settings()
    domain = _build_domain(settings.data_source, snapshot_fecha)

    if settings.system_store is SystemStore.turso and settings.data_source is not DataSource.turso:
        from nexo_os.data.composite import CompositeRepository
        from nexo_os.data.turso import TursoRepository

        system = TursoRepository(snapshot_fecha=snapshot_fecha)
        return CompositeRepository(domain=domain, system=system)

    return domain
