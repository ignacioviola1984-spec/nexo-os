"""CompositeRepository — domain reads from one backend, system tables from another.

Powers the hybrid mode (NEXO_SYSTEM_STORE=turso): domain data keeps coming from the
synthetic or BigQuery backend, while the system tables (acciones, agent_runs,
audit_log) are read/written in hosted Turso so approvals and the hash-chained audit
log persist across Streamlit Cloud restarts. Pure delegation — no SQL of its own.
"""

from __future__ import annotations

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
from nexo_os.data.repository import NexoRepository


class CompositeRepository(NexoRepository):
    def __init__(self, domain: NexoRepository, system: NexoRepository) -> None:
        self._domain = domain
        self._system = system
        # Identify the live composition on each run, e.g. "synthetic+turso".
        self.data_source = f"{domain.data_source}+{system.data_source}"

    @property
    def snapshot_fecha(self) -> date:
        return self._domain.snapshot_fecha

    # --- domain reads -> domain backend ---------------------------------------

    def get_clientes(self, estado: ClienteEstado | None = None) -> list[Cliente]:
        return self._domain.get_clientes(estado)

    def get_polizas(
        self, estado: PolizaEstado | None = None, ramo: Ramo | None = None
    ) -> list[Poliza]:
        return self._domain.get_polizas(estado, ramo)

    def get_cuotas(self, estado: CuotaEstado | None = None) -> list[Cuota]:
        return self._domain.get_cuotas(estado)

    def get_comisiones(
        self, periodo: str | None = None, estado: ComisionEstado | None = None
    ) -> list[Comision]:
        return self._domain.get_comisiones(periodo, estado)

    def get_leads(self, estado: LeadEstado | None = None) -> list[Lead]:
        return self._domain.get_leads(estado)

    def get_cotizaciones(self, estado: CotizacionEstado | None = None) -> list[Cotizacion]:
        return self._domain.get_cotizaciones(estado)

    def get_siniestros(self, estado: SiniestroEstado | None = None) -> list[Siniestro]:
        return self._domain.get_siniestros(estado)

    def get_aseguradoras(self) -> list[Aseguradora]:
        return self._domain.get_aseguradoras()

    def get_productores(self) -> list[Productor]:
        return self._domain.get_productores()

    def get_interacciones(self, entidad_tipo: EntidadTipo | None = None) -> list[Interaccion]:
        return self._domain.get_interacciones(entidad_tipo)

    # --- system tables -> system backend --------------------------------------

    def insert_acciones(self, acciones: list[Accion]) -> None:
        self._system.insert_acciones(acciones)

    def get_acciones(
        self, estado: AccionEstado | None = None, run_id: str | None = None
    ) -> list[Accion]:
        return self._system.get_acciones(estado, run_id)

    def get_accion(self, accion_id: str) -> Accion | None:
        return self._system.get_accion(accion_id)

    def resolve_accion(
        self,
        accion_id: str,
        estado: AccionEstado,
        resuelta_en: datetime,
        resuelta_por: str,
        nota_revisor: str | None = None,
        mensaje_es: str | None = None,
    ) -> None:
        self._system.resolve_accion(
            accion_id, estado, resuelta_en, resuelta_por, nota_revisor, mensaje_es
        )

    def insert_agent_run(self, run: AgentRun) -> None:
        self._system.insert_agent_run(run)

    def update_agent_run(
        self, run_id: str, finalizado_en: datetime, estado: RunEstado, resumen_json: str
    ) -> None:
        self._system.update_agent_run(run_id, finalizado_en, estado, resumen_json)

    def get_agent_runs(self) -> list[AgentRun]:
        return self._system.get_agent_runs()

    def append_audit_event(self, event: AuditEvent) -> None:
        self._system.append_audit_event(event)

    def get_audit_events(self) -> list[AuditEvent]:
        return self._system.get_audit_events()

    def get_last_audit_hash(self) -> str | None:
        return self._system.get_last_audit_hash()

    def close(self) -> None:
        for repo in (self._domain, self._system):
            close = getattr(repo, "close", None)
            if callable(close):
                close()
