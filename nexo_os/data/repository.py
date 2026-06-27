"""The data-access boundary. Agents and core never read a file or run a query
directly — they call typed methods here and get typed domain objects back.

An agent's code is identical whether data came from synthetic or BigQuery; only the
factory and settings change. No untyped dict crosses this boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime

from nexo_os.data.models import (
    Accion,
    AccionEstado,
    AgentRun,
    Aseguradora,
    AuditEvent,
    Cliente,
    ClienteEstado,
    Comision,
    ComisionEstado,
    Cotizacion,
    CotizacionEstado,
    Cuota,
    CuotaEstado,
    EntidadTipo,
    Interaccion,
    Lead,
    LeadEstado,
    Poliza,
    PolizaEstado,
    Productor,
    Ramo,
    RunEstado,
    Siniestro,
    SiniestroEstado,
)


class RepositoryError(RuntimeError):
    """Base for data-access failures. Always fail closed with a clear message."""


class DataSourceUnavailable(RepositoryError):
    """The selected backend cannot be reached / is not configured. Never fabricate
    or stub data to look live."""


class NexoRepository(ABC):
    """Read access to the canonical domain tables + read/write of the system tables."""

    #: Backend identifier, persisted on each run ('synthetic' | 'bigquery').
    data_source: str

    @property
    @abstractmethod
    def snapshot_fecha(self) -> date:
        """The 'as of' date all reads are interpreted against."""

    # --- domain reads ---------------------------------------------------------

    @abstractmethod
    def get_clientes(self, estado: ClienteEstado | None = None) -> list[Cliente]: ...

    @abstractmethod
    def get_polizas(
        self, estado: PolizaEstado | None = None, ramo: Ramo | None = None
    ) -> list[Poliza]: ...

    @abstractmethod
    def get_cuotas(self, estado: CuotaEstado | None = None) -> list[Cuota]: ...

    @abstractmethod
    def get_comisiones(
        self, periodo: str | None = None, estado: ComisionEstado | None = None
    ) -> list[Comision]: ...

    @abstractmethod
    def get_leads(self, estado: LeadEstado | None = None) -> list[Lead]: ...

    @abstractmethod
    def get_cotizaciones(self, estado: CotizacionEstado | None = None) -> list[Cotizacion]: ...

    @abstractmethod
    def get_siniestros(self, estado: SiniestroEstado | None = None) -> list[Siniestro]: ...

    @abstractmethod
    def get_aseguradoras(self) -> list[Aseguradora]: ...

    @abstractmethod
    def get_productores(self) -> list[Productor]: ...

    @abstractmethod
    def get_interacciones(self, entidad_tipo: EntidadTipo | None = None) -> list[Interaccion]: ...

    # --- system tables: acciones (the HITL inbox) -----------------------------

    @abstractmethod
    def insert_acciones(self, acciones: list[Accion]) -> None: ...

    @abstractmethod
    def get_acciones(
        self, estado: AccionEstado | None = None, run_id: str | None = None
    ) -> list[Accion]: ...

    @abstractmethod
    def get_accion(self, accion_id: str) -> Accion | None: ...

    @abstractmethod
    def resolve_accion(
        self,
        accion_id: str,
        estado: AccionEstado,
        resuelta_en: datetime,
        resuelta_por: str,
        nota_revisor: str | None = None,
        mensaje_es: str | None = None,
    ) -> None:
        """Record a HITL decision on an action (aprobada/rechazada/editada)."""

    # --- system tables: agent_runs --------------------------------------------

    @abstractmethod
    def insert_agent_run(self, run: AgentRun) -> None: ...

    @abstractmethod
    def update_agent_run(
        self,
        run_id: str,
        finalizado_en: datetime,
        estado: RunEstado,
        resumen_json: str,
    ) -> None: ...

    @abstractmethod
    def get_agent_runs(self) -> list[AgentRun]: ...

    # --- system tables: audit_log (append-only, hash-chained) -----------------

    @abstractmethod
    def append_audit_event(self, event: AuditEvent) -> None:
        """Append a single audit event. Application code never updates or deletes."""

    @abstractmethod
    def get_audit_events(self) -> list[AuditEvent]: ...

    @abstractmethod
    def get_last_audit_hash(self) -> str | None:
        """The hash of the most recent audit row, or None if the log is empty."""
