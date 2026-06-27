"""Renovaciones (renewals): policies expiring in 30/60/90 days, premium at stake,
and at-risk renewals (claim history and/or overdue, no successor). Proposes
prioritized renewal outreach."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core.aging import is_overdue
from nexo_os.core.money import ZERO, q2, ratio
from nexo_os.core.results import Hallazgo
from nexo_os.data.models import Cuota, Poliza, PolizaEstado, Siniestro

AGENTE = "renewals"


@dataclass(frozen=True)
class RenewalsResult:
    expira_30_count: int
    expira_60_count: int
    expira_90_count: int
    expira_total_90d_count: int
    prima_en_riesgo_90d_ars: Decimal
    at_risk_ids: list[str]
    at_risk_prima_ars: Decimal
    renewal_rate: Decimal | None
    hallazgos: list[Hallazgo] = field(default_factory=list)


def compute(
    polizas: list[Poliza],
    siniestros: list[Siniestro],
    cuotas: list[Cuota],
    snapshot: date,
    thresholds: Thresholds,
) -> RenewalsResult:
    w30, w60, w90 = thresholds.expiry_windows_days
    successors = {p.poliza_origen_id for p in polizas if p.poliza_origen_id is not None}
    claims_by_policy: dict[str, int] = {}
    for s in siniestros:
        claims_by_policy[s.poliza_id] = claims_by_policy.get(s.poliza_id, 0) + 1
    overdue_policies = {c.poliza_id for c in cuotas if is_overdue(c, snapshot)}

    c30 = c60 = c90 = 0
    prima_riesgo = ZERO
    at_risk_ids: list[str] = []
    at_risk_prima = ZERO
    hallazgos: list[Hallazgo] = []

    for p in polizas:
        if p.estado is not PolizaEstado.vigente:
            continue
        dias = (p.fecha_fin_vigencia - snapshot).days
        if dias < 0 or dias > w90:
            continue
        if p.poliza_id in successors:
            continue  # already renewed (has a successor term)
        if dias <= w30:
            c30 += 1
        elif dias <= w60:
            c60 += 1
        else:
            c90 += 1
        prima_riesgo += p.prima_ars

        has_claim = claims_by_policy.get(p.poliza_id, 0) > 0
        has_overdue = p.poliza_id in overdue_policies
        at_risk = has_claim or has_overdue
        if at_risk:
            at_risk_ids.append(p.poliza_id)
            at_risk_prima += p.prima_ars
        hallazgos.append(
            Hallazgo(
                agente=AGENTE,
                tipo_accion="gestionar_renovacion",
                entidad_tipo="poliza",
                entidad_id=p.poliza_id,
                monto_en_juego_ars=q2(p.prima_ars),
                urgencia_dias=dias,
                numeros={
                    "poliza_id": p.poliza_id,
                    "cliente_id": p.cliente_id,
                    "dias_a_vencimiento": dias,
                    "prima_ars": str(q2(p.prima_ars)),
                    "en_riesgo": at_risk,
                    "tiene_siniestro": has_claim,
                    "tiene_mora": has_overdue,
                },
                completitud=1.0,
                senial=1.0 if at_risk else max(0.3, 1.0 - dias / 90),
            )
        )

    # renewal rate needs renovada/vencida history; None when there is no basis
    renovadas = sum(1 for p in polizas if p.estado is PolizaEstado.renovada)
    vencidas = sum(1 for p in polizas if p.estado is PolizaEstado.vencida)
    renewal_rate = ratio(Decimal(renovadas), Decimal(renovadas + vencidas))

    return RenewalsResult(
        expira_30_count=c30,
        expira_60_count=c60,
        expira_90_count=c90,
        expira_total_90d_count=c30 + c60 + c90,
        prima_en_riesgo_90d_ars=q2(prima_riesgo),
        at_risk_ids=sorted(at_risk_ids),
        at_risk_prima_ars=q2(at_risk_prima),
        renewal_rate=renewal_rate,
        hallazgos=hallazgos,
    )
