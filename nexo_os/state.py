"""NexoContext — the shared, auditable state book for a run. Agents read prior
agents' results from it and write their own. Repository reads are memoized so all
agents compute against one consistent snapshot, fetched once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from functools import cached_property

from nexo_os.config import Thresholds, get_settings
from nexo_os.data.models import (
    Accion,
    Aseguradora,
    Cliente,
    Comision,
    Cotizacion,
    Cuota,
    Interaccion,
    Lead,
    Poliza,
    Productor,
    Siniestro,
)
from nexo_os.data.repository import NexoRepository


@dataclass
class NexoContext:
    repo: NexoRepository
    run_id: str
    snapshot_fecha: date
    thresholds: Thresholds = field(default_factory=lambda: get_settings().thresholds)

    results: dict[str, object] = field(default_factory=dict)
    acciones: list[Accion] = field(default_factory=list)
    warnings: list[tuple[str, str]] = field(default_factory=list)  # (severidad, mensaje)

    # --- memoized snapshot reads (fetched once, shared by all agents) ----------

    @cached_property
    def clientes(self) -> list[Cliente]:
        return self.repo.get_clientes()

    @cached_property
    def polizas(self) -> list[Poliza]:
        return self.repo.get_polizas()

    @cached_property
    def cuotas(self) -> list[Cuota]:
        return self.repo.get_cuotas()

    @cached_property
    def comisiones(self) -> list[Comision]:
        return self.repo.get_comisiones()

    @cached_property
    def comisiones_periodo_actual(self) -> list[Comision]:
        periodo = f"{self.snapshot_fecha.year:04d}-{self.snapshot_fecha.month:02d}"
        return [c for c in self.comisiones if c.periodo == periodo]

    @cached_property
    def leads(self) -> list[Lead]:
        return self.repo.get_leads()

    @cached_property
    def cotizaciones(self) -> list[Cotizacion]:
        return self.repo.get_cotizaciones()

    @cached_property
    def siniestros(self) -> list[Siniestro]:
        return self.repo.get_siniestros()

    @cached_property
    def aseguradoras(self) -> list[Aseguradora]:
        return self.repo.get_aseguradoras()

    @cached_property
    def productores(self) -> list[Productor]:
        return self.repo.get_productores()

    @cached_property
    def interacciones(self) -> list[Interaccion]:
        return self.repo.get_interacciones()

    # --- writes ---------------------------------------------------------------

    def put_result(self, agente: str, result: object) -> None:
        self.results[agente] = result

    def get_result(self, agente: str) -> object | None:
        return self.results.get(agente)

    def add_acciones(self, acciones: list[Accion]) -> None:
        self.acciones.extend(acciones)

    def add_warning(self, severidad: str, mensaje: str) -> None:
        self.warnings.append((severidad, mensaje))

    # --- summary --------------------------------------------------------------

    def summary_line(self) -> str:
        return (
            f"run {self.run_id} @ {self.snapshot_fecha} | "
            f"{len(self.acciones)} acciones propuestas | {len(self.warnings)} warnings"
        )

    def resumen(self) -> dict:
        por_agente: dict[str, int] = {}
        monto_total = Decimal("0")
        for a in self.acciones:
            por_agente[a.agente] = por_agente.get(a.agente, 0) + 1
            if a.monto_en_juego_ars is not None:
                monto_total += a.monto_en_juego_ars
        return {
            "acciones_total": len(self.acciones),
            "acciones_por_agente": por_agente,
            "monto_en_juego_total_ars": str(monto_total),
            "warnings": [{"severidad": s, "mensaje": m} for s, m in self.warnings],
        }
