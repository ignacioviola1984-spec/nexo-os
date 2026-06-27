"""Morosidad (delinquency): measures the risk — overdue rate, aging distribution,
and deteriorating buckets. Cobranza acts on the same overdue universe (their shared
totals reconcile in the orchestrator)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core.aging import (
    ALL_BUCKETS,
    bucket_mora,
    dias_mora,
    is_overdue,
    is_unpaid,
    outstanding,
)
from nexo_os.core.money import ZERO, dsum, q2, ratio
from nexo_os.core.results import Hallazgo
from nexo_os.data.models import Cuota

AGENTE = "morosidad"
DETERIORATING = {"61-90", "90+"}


@dataclass(frozen=True)
class MorosidadResult:
    total_vencido_ars: Decimal
    total_vencido_count: int
    por_bucket: dict[str, dict]  # bucket -> {count, ars}
    tasa_morosidad_ars: Decimal | None
    tasa_morosidad_count: Decimal | None
    cuota_ids: list[str]
    hallazgos: list[Hallazgo] = field(default_factory=list)


def compute(cuotas: list[Cuota], snapshot: date, thresholds: Thresholds) -> MorosidadResult:
    overdue = [c for c in cuotas if is_overdue(c, snapshot)]
    por_bucket: dict[str, dict] = {b: {"count": 0, "ars": ZERO} for b in ALL_BUCKETS}
    for c in overdue:
        b = bucket_mora(dias_mora(c.fecha_vencimiento, snapshot), thresholds.mora)
        por_bucket[b]["count"] += 1
        por_bucket[b]["ars"] += outstanding(c)

    total_ars = dsum(outstanding(c) for c in overdue)
    total_count = len(overdue)

    unpaid = [c for c in cuotas if is_unpaid(c)]
    total_outstanding = dsum(outstanding(c) for c in unpaid)
    tasa_ars = ratio(total_ars, total_outstanding)
    tasa_count = ratio(Decimal(total_count), Decimal(len(unpaid)))

    hallazgos: list[Hallazgo] = []
    for b in DETERIORATING:
        info = por_bucket[b]
        if info["count"] > 0:
            hallazgos.append(
                Hallazgo(
                    agente=AGENTE,
                    tipo_accion="escalar_segmento_mora",
                    entidad_tipo="bucket",
                    entidad_id=b,
                    monto_en_juego_ars=q2(info["ars"]),
                    urgencia_dias=90 if b == "90+" else 75,
                    numeros={
                        "bucket": b,
                        "count": info["count"],
                        "ars": str(q2(info["ars"])),
                        "total_vencido_ars": str(q2(total_ars)),
                    },
                    completitud=1.0,
                    senial=1.0 if b == "90+" else 0.7,
                )
            )

    return MorosidadResult(
        total_vencido_ars=q2(total_ars),
        total_vencido_count=total_count,
        por_bucket={b: {"count": v["count"], "ars": q2(v["ars"])} for b, v in por_bucket.items()},
        tasa_morosidad_ars=tasa_ars,
        tasa_morosidad_count=tasa_count,
        cuota_ids=sorted(c.cuota_id for c in overdue),
        hallazgos=hallazgos,
    )
