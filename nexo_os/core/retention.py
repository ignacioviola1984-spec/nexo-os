"""Revenue retention: commission at risk from churn signals, quantified per client.
Two deterministic signals are implemented (others are extensible): long INACTIVITY
and LAPSE (a 90+ overdue installment). Ranks by commission at risk."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core.aging import dias_mora, is_overdue
from nexo_os.core.money import ZERO, dsum, q2
from nexo_os.core.results import Hallazgo
from nexo_os.data.models import Cuota, Interaccion, Poliza, PolizaEstado

AGENTE = "retention"


@dataclass(frozen=True)
class RetentionResult:
    at_risk_count: int
    comision_en_riesgo_ars: Decimal
    at_risk_client_ids: list[str]
    hallazgos: list[Hallazgo] = field(default_factory=list)


def compute(
    polizas: list[Poliza],
    cuotas: list[Cuota],
    interacciones: list[Interaccion],
    snapshot: date,
    thresholds: Thresholds,
) -> RetentionResult:
    # in-force commission per client (= sum of premium x pct over vigente policies)
    commission_by_client: dict[str, Decimal] = {}
    inforce_policies_by_client: dict[str, list[Poliza]] = {}
    for p in polizas:
        if p.estado is PolizaEstado.vigente:
            commission_by_client[p.cliente_id] = q2(
                commission_by_client.get(p.cliente_id, ZERO) + p.prima_ars * p.comision_pct
            )
            inforce_policies_by_client.setdefault(p.cliente_id, []).append(p)

    # last interaction date per client
    last_interaction: dict[str, date] = {}
    for i in interacciones:
        if i.entidad_tipo.value == "cliente":
            prev = last_interaction.get(i.entidad_id)
            if prev is None or i.fecha > prev:
                last_interaction[i.entidad_id] = i.fecha

    # lapse signal: clients with a 90+ overdue installment
    pol_client = {p.poliza_id: p.cliente_id for p in polizas}
    lapse_clients: set[str] = set()
    for c in cuotas:
        if (
            is_overdue(c, snapshot)
            and dias_mora(c.fecha_vencimiento, snapshot) > thresholds.mora.b61_90
        ):
            cid = pol_client.get(c.poliza_id)
            if cid is not None:
                lapse_clients.add(cid)

    hallazgos: list[Hallazgo] = []
    at_risk_ids: list[str] = []
    for cid in inforce_policies_by_client:
        li = last_interaction.get(cid)
        inactivity = li is None or (snapshot - li).days > thresholds.inactivity_days
        lapse = cid in lapse_clients
        if not (inactivity or lapse):
            continue
        at_risk_ids.append(cid)
        monto = commission_by_client[cid]
        signals = [s for s, on in (("inactividad", inactivity), ("lapso", lapse)) if on]
        dias_inact = (snapshot - li).days if li is not None else None
        hallazgos.append(
            Hallazgo(
                agente=AGENTE,
                tipo_accion="retener_cliente",
                entidad_tipo="cliente",
                entidad_id=cid,
                monto_en_juego_ars=monto,
                urgencia_dias=dias_inact,
                numeros={
                    "cliente_id": cid,
                    "comision_en_riesgo_ars": str(monto),
                    "señales": ",".join(signals),
                    "polizas_vigentes": len(inforce_policies_by_client[cid]),
                },
                completitud=1.0,
                senial=1.0 if lapse else 0.7,
            )
        )
    hallazgos.sort(key=lambda h: h.monto_en_juego_ars or ZERO, reverse=True)
    total = dsum(commission_by_client[c] for c in at_risk_ids)

    return RetentionResult(
        at_risk_count=len(at_risk_ids),
        comision_en_riesgo_ars=q2(total),
        at_risk_client_ids=sorted(at_risk_ids),
        hallazgos=hallazgos,
    )
