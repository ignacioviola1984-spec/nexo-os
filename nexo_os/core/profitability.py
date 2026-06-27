"""Profitability by product/portfolio: net commission, loss ratio (claims paid vs
premium) and ranking by ramo. Proposes review of unprofitable segments."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core.money import ZERO, q2, ratio
from nexo_os.core.results import Hallazgo
from nexo_os.data.models import Poliza, PolizaEstado, Siniestro, SiniestroEstado

AGENTE = "profitability"


@dataclass(frozen=True)
class ProfitabilityResult:
    por_ramo: dict[str, dict]  # ramo -> {prima, comision_neta, siniestros_pagados, loss_ratio}
    ramos_no_rentables: list[str]
    hallazgos: list[Hallazgo] = field(default_factory=list)


def compute(
    polizas: list[Poliza], siniestros: list[Siniestro], thresholds: Thresholds
) -> ProfitabilityResult:
    vigentes = [p for p in polizas if p.estado is PolizaEstado.vigente]
    ramo_of = {p.poliza_id: p.ramo.value for p in polizas}

    prima_by_ramo: dict[str, Decimal] = {}
    comision_by_ramo: dict[str, Decimal] = {}
    for p in vigentes:
        r = p.ramo.value
        prima_by_ramo[r] = prima_by_ramo.get(r, ZERO) + p.prima_ars
        comision_by_ramo[r] = comision_by_ramo.get(r, ZERO) + p.prima_ars * p.comision_pct

    claims_by_ramo: dict[str, Decimal] = {}
    for s in siniestros:
        if s.estado is SiniestroEstado.pagado and s.monto_pagado_ars is not None:
            r = ramo_of.get(s.poliza_id)
            if r is not None:
                claims_by_ramo[r] = claims_by_ramo.get(r, ZERO) + s.monto_pagado_ars

    por_ramo: dict[str, dict] = {}
    no_rentables: list[str] = []
    hallazgos: list[Hallazgo] = []
    alert = Decimal(str(thresholds.loss_ratio_alert))
    for r, prima in prima_by_ramo.items():
        claims = claims_by_ramo.get(r, ZERO)
        lr = ratio(claims, prima)
        por_ramo[r] = {
            "prima_ars": q2(prima),
            "comision_neta_ars": q2(comision_by_ramo.get(r, ZERO)),
            "siniestros_pagados_ars": q2(claims),
            "loss_ratio": lr,
        }
        if lr is not None and lr > alert:
            no_rentables.append(r)
            hallazgos.append(
                Hallazgo(
                    agente=AGENTE,
                    tipo_accion="revisar_segmento_no_rentable",
                    entidad_tipo="ramo",
                    entidad_id=r,
                    monto_en_juego_ars=q2(claims),
                    urgencia_dias=None,
                    numeros={
                        "ramo": r,
                        "prima_ars": str(q2(prima)),
                        "siniestros_pagados_ars": str(q2(claims)),
                        "loss_ratio": str(lr),
                        "umbral": str(thresholds.loss_ratio_alert),
                    },
                    completitud=1.0,
                    senial=min(1.0, float(lr / alert) - 0.5),
                )
            )

    return ProfitabilityResult(
        por_ramo=por_ramo,
        ramos_no_rentables=sorted(no_rentables),
        hallazgos=hallazgos,
    )
