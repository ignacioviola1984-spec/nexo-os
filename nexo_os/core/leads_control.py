"""Control de leads/cotizaciones: SLA breaches, quotes issued but never presented,
and leads with no quote past a window. Keeps the funnel honest (data hygiene + SLA)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from nexo_os.config import Thresholds
from nexo_os.core.results import Hallazgo
from nexo_os.data.models import Cotizacion, CotizacionEstado, Lead, LeadEstado

AGENTE = "leads_control"
OPEN_STATES = {LeadEstado.nuevo, LeadEstado.contactado, LeadEstado.cotizado, LeadEstado.presentado}


@dataclass(frozen=True)
class LeadsControlResult:
    sla_breach_count: int
    quotes_no_presentadas_count: int
    leads_sin_cotizacion_count: int
    sla_breach_ids: list[str]
    quotes_no_presentadas_ids: list[str]
    hallazgos: list[Hallazgo] = field(default_factory=list)


def compute(
    leads: list[Lead],
    cotizaciones: list[Cotizacion],
    snapshot: date,
    thresholds: Thresholds,
) -> LeadsControlResult:
    quotes_by_lead: dict[str, list[Cotizacion]] = {}
    for c in cotizaciones:
        quotes_by_lead.setdefault(c.lead_id, []).append(c)

    hallazgos: list[Hallazgo] = []
    sla_ids: list[str] = []
    sla_lead_set: set[str] = set()

    for ld in leads:
        if ld.estado not in OPEN_STATES:
            continue
        dias = (snapshot - ld.fecha_ultimo_movimiento).days
        if dias > thresholds.lead_sla_days:
            sla_ids.append(ld.lead_id)
            sla_lead_set.add(ld.lead_id)
            hallazgos.append(
                Hallazgo(
                    agente=AGENTE,
                    tipo_accion="contactar_lead_sla",
                    entidad_tipo="lead",
                    entidad_id=ld.lead_id,
                    monto_en_juego_ars=None,
                    urgencia_dias=dias,
                    numeros={
                        "lead_id": ld.lead_id,
                        "estado": ld.estado.value,
                        "dias_sin_movimiento": dias,
                        "sla_dias": thresholds.lead_sla_days,
                    },
                    completitud=1.0,
                    senial=min(1.0, dias / 30),
                )
            )

    # quotes issued (emitida) but never presented, past the window
    np_ids: list[str] = []
    for c in cotizaciones:
        if c.estado is CotizacionEstado.emitida:
            dias = (snapshot - c.fecha_cotizacion).days
            if dias > thresholds.quote_not_presented_days:
                np_ids.append(c.cotizacion_id)
                hallazgos.append(
                    Hallazgo(
                        agente=AGENTE,
                        tipo_accion="presentar_cotizacion",
                        entidad_tipo="cotizacion",
                        entidad_id=c.cotizacion_id,
                        monto_en_juego_ars=None,
                        urgencia_dias=dias,
                        numeros={
                            "cotizacion_id": c.cotizacion_id,
                            "lead_id": c.lead_id,
                            "dias_sin_presentar": dias,
                        },
                        completitud=1.0,
                        senial=min(1.0, dias / 30),
                    )
                )

    # leads with no quote past a window (excluding those already flagged for SLA,
    # to avoid double-surfacing the same lead)
    sin_cot = 0
    for ld in leads:
        if ld.estado not in OPEN_STATES or ld.lead_id in sla_lead_set:
            continue
        if quotes_by_lead.get(ld.lead_id):
            continue
        if (snapshot - ld.fecha_ingreso).days > thresholds.lead_no_quote_days:
            sin_cot += 1
            hallazgos.append(
                Hallazgo(
                    agente=AGENTE,
                    tipo_accion="cotizar_lead",
                    entidad_tipo="lead",
                    entidad_id=ld.lead_id,
                    monto_en_juego_ars=None,
                    urgencia_dias=(snapshot - ld.fecha_ingreso).days,
                    numeros={"lead_id": ld.lead_id, "estado": ld.estado.value},
                    completitud=1.0,
                    senial=0.5,
                )
            )

    return LeadsControlResult(
        sla_breach_count=len(sla_ids),
        quotes_no_presentadas_count=len(np_ids),
        leads_sin_cotizacion_count=sin_cot,
        sla_breach_ids=sorted(sla_ids),
        quotes_no_presentadas_ids=sorted(np_ids),
        hallazgos=hallazgos,
    )
