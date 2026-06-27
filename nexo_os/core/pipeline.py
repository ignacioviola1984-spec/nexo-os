"""Pipeline: open value, stage distribution, weighted forecast (deterministic stage
probabilities), and aging. Proposes next-step actions on aging/high-value opportunities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core.money import ZERO, dsum, q2
from nexo_os.core.results import Hallazgo
from nexo_os.data.models import Cotizacion, Lead, LeadEstado

AGENTE = "pipeline"
OPEN_STATES = {LeadEstado.nuevo, LeadEstado.contactado, LeadEstado.cotizado, LeadEstado.presentado}


@dataclass(frozen=True)
class PipelineResult:
    open_count: int
    open_value_ars: Decimal
    forecast_ponderado_ars: Decimal
    distribucion_etapa: dict[str, int]
    hallazgos: list[Hallazgo] = field(default_factory=list)


def compute(
    leads: list[Lead], cotizaciones: list[Cotizacion], snapshot: date, thresholds: Thresholds
) -> PipelineResult:
    value_by_lead: dict[str, Decimal] = {}
    for c in cotizaciones:
        prev = value_by_lead.get(c.lead_id, ZERO)
        if c.prima_cotizada_ars > prev:
            value_by_lead[c.lead_id] = c.prima_cotizada_ars

    probs = thresholds.stage_probabilities
    open_leads = [ld for ld in leads if ld.estado in OPEN_STATES]
    open_value = dsum(value_by_lead.get(ld.lead_id, ZERO) for ld in open_leads)

    forecast = ZERO
    distrib: dict[str, int] = {}
    for ld in open_leads:
        distrib_key = ld.estado.value
        distrib[distrib_key] = distrib.get(distrib_key, 0) + 1
        val = value_by_lead.get(ld.lead_id, ZERO)
        forecast += val * Decimal(str(probs.get(ld.estado.value, 0.0)))

    hallazgos: list[Hallazgo] = []
    for ld in open_leads:
        dias_en_etapa = (snapshot - ld.fecha_ultimo_movimiento).days
        if dias_en_etapa > thresholds.pipeline_aging_days:
            val = value_by_lead.get(ld.lead_id, ZERO)
            hallazgos.append(
                Hallazgo(
                    agente=AGENTE,
                    tipo_accion="avanzar_oportunidad",
                    entidad_tipo="lead",
                    entidad_id=ld.lead_id,
                    monto_en_juego_ars=q2(val) if val > ZERO else None,
                    urgencia_dias=dias_en_etapa,
                    numeros={
                        "lead_id": ld.lead_id,
                        "etapa": ld.estado.value,
                        "dias_en_etapa": dias_en_etapa,
                        "valor_estimado_ars": str(q2(val)),
                    },
                    completitud=1.0,
                    senial=min(1.0, dias_en_etapa / 60),
                )
            )

    return PipelineResult(
        open_count=len(open_leads),
        open_value_ars=q2(open_value),
        forecast_ponderado_ars=q2(forecast),
        distribucion_etapa=distrib,
        hallazgos=hallazgos,
    )
