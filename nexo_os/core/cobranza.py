"""Cobranza (collections): outstanding by bucket, DSO, and a prioritized recovery
list (amount x age x client value). Its overdue total reconciles with morosidad."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core.aging import bucket_mora, dias_mora, is_overdue, outstanding
from nexo_os.core.money import ZERO, dsum, q2, ratio
from nexo_os.core.results import Hallazgo
from nexo_os.data.models import Cuota, Poliza, PolizaEstado

AGENTE = "cobranza"


@dataclass(frozen=True)
class CobranzaResult:
    total_vencido_ars: Decimal
    total_vencido_count: int
    dso_dias: Decimal | None
    hallazgos: list[Hallazgo] = field(default_factory=list)


def compute(
    cuotas: list[Cuota], polizas: list[Poliza], snapshot: date, thresholds: Thresholds
) -> CobranzaResult:
    pol_by_id = {p.poliza_id: p for p in polizas}
    # client value proxy: in-force premium per client
    client_value: dict[str, Decimal] = {}
    for p in polizas:
        if p.estado is PolizaEstado.vigente:
            client_value[p.cliente_id] = client_value.get(p.cliente_id, ZERO) + p.prima_ars

    overdue = [c for c in cuotas if is_overdue(c, snapshot)]
    total_ars = dsum(outstanding(c) for c in overdue)

    # DSO proxy: amount-weighted average days overdue
    weighted_days = dsum(
        Decimal(dias_mora(c.fecha_vencimiento, snapshot)) * outstanding(c) for c in overdue
    )
    dso = ratio(weighted_days, total_ars)

    hallazgos: list[Hallazgo] = []
    for c in overdue:
        pol = pol_by_id.get(c.poliza_id)
        cliente_id = pol.cliente_id if pol else "desconocido"
        dias = dias_mora(c.fecha_vencimiento, snapshot)
        monto = outstanding(c)
        cval = client_value.get(cliente_id, ZERO)
        # deterministic recovery priority score (higher = collect first)
        age_factor = Decimal(min(dias, 180)) / Decimal(30)
        value_factor = Decimal(1) + (cval / Decimal(1_000_000))
        score = q2(monto * age_factor * value_factor)
        hallazgos.append(
            Hallazgo(
                agente=AGENTE,
                tipo_accion="gestionar_cobro",
                entidad_tipo="cliente",
                entidad_id=cliente_id,
                monto_en_juego_ars=q2(monto),
                urgencia_dias=dias,
                numeros={
                    "cuota_id": c.cuota_id,
                    "poliza_id": c.poliza_id,
                    "monto_vencido_ars": str(q2(monto)),
                    "dias_mora": dias,
                    "bucket": bucket_mora(dias, thresholds.mora),
                    "score_recupero": str(score),
                    "valor_cliente_ars": str(q2(cval)),
                },
                completitud=1.0 if pol else 0.5,
                senial=min(1.0, dias / 90),
            )
        )
    # highest recoverable first
    hallazgos.sort(key=lambda h: Decimal(h.numeros["score_recupero"]), reverse=True)

    return CobranzaResult(
        total_vencido_ars=q2(total_ars),
        total_vencido_count=len(overdue),
        dso_dias=dso,
        hallazgos=hallazgos,
    )
