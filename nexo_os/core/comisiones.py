"""Seguimiento de comisiones (commission tracking): expected vs settled, discrepancies,
and aging of commission receivable per insurer. Protects the broker's revenue —
treated with settlement-grade rigor."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core.money import ZERO, dsum, q2
from nexo_os.core.results import Hallazgo
from nexo_os.data.models import Comision, ComisionEstado

AGENTE = "comisiones"


@dataclass(frozen=True)
class ComisionesResult:
    esperada_total_ars: Decimal
    liquidada_total_ars: Decimal
    diferencia_total_ars: Decimal
    receivable_vencido_ars: Decimal
    por_aseguradora: dict[str, dict]
    discrepancia_ids: list[str]
    receivable_vencido_ids: list[str]
    hallazgos: list[Hallazgo] = field(default_factory=list)


def period_end(periodo: str) -> date:
    """Last calendar day of a 'YYYY-MM' period."""
    y, m = (int(x) for x in periodo.split("-"))
    return date(y, m, calendar.monthrange(y, m)[1])


def compute(comisiones: list[Comision], snapshot: date, thresholds: Thresholds) -> ComisionesResult:
    esperada_total = dsum(c.comision_esperada_ars for c in comisiones)
    liquidada_total = dsum(c.comision_liquidada_ars or ZERO for c in comisiones)

    por_aseg: dict[str, dict] = {}
    for c in comisiones:
        a = por_aseg.setdefault(
            c.aseguradora_id, {"esperada": ZERO, "liquidada": ZERO, "diferencia": ZERO}
        )
        a["esperada"] += c.comision_esperada_ars
        a["liquidada"] += c.comision_liquidada_ars or ZERO

    hallazgos: list[Hallazgo] = []
    disc_ids: list[str] = []
    recv_ids: list[str] = []
    diferencia_total = ZERO
    receivable_total = ZERO

    for c in comisiones:
        # (a) discrepancy: settled below expected
        if c.estado is ComisionEstado.con_diferencia and c.diferencia_ars > ZERO:
            disc_ids.append(c.comision_id)
            diferencia_total += c.diferencia_ars
            por_aseg[c.aseguradora_id]["diferencia"] += c.diferencia_ars
            hallazgos.append(
                Hallazgo(
                    agente=AGENTE,
                    tipo_accion="reclamar_diferencia_comision",
                    entidad_tipo="comision",
                    entidad_id=c.comision_id,
                    monto_en_juego_ars=q2(c.diferencia_ars),
                    urgencia_dias=(snapshot - period_end(c.periodo)).days,
                    numeros={
                        "comision_id": c.comision_id,
                        "aseguradora_id": c.aseguradora_id,
                        "periodo": c.periodo,
                        "esperada_ars": str(q2(c.comision_esperada_ars)),
                        "liquidada_ars": str(q2(c.comision_liquidada_ars or ZERO)),
                        "diferencia_ars": str(q2(c.diferencia_ars)),
                    },
                    completitud=1.0,
                    senial=1.0,
                )
            )
        # (b) aged receivable: unsettled (or under-settled) past the overdue window
        elif c.estado in (ComisionEstado.esperada, ComisionEstado.parcial):
            pendiente = c.comision_esperada_ars - (c.comision_liquidada_ars or ZERO)
            age = (snapshot - period_end(c.periodo)).days
            if pendiente > ZERO and age > thresholds.commission_overdue_days:
                recv_ids.append(c.comision_id)
                receivable_total += pendiente
                hallazgos.append(
                    Hallazgo(
                        agente=AGENTE,
                        tipo_accion="gestionar_comision_por_cobrar",
                        entidad_tipo="comision",
                        entidad_id=c.comision_id,
                        monto_en_juego_ars=q2(pendiente),
                        urgencia_dias=age,
                        numeros={
                            "comision_id": c.comision_id,
                            "aseguradora_id": c.aseguradora_id,
                            "periodo": c.periodo,
                            "pendiente_ars": str(q2(pendiente)),
                            "dias_aging": age,
                        },
                        completitud=1.0,
                        senial=min(1.0, age / 90),
                    )
                )

    return ComisionesResult(
        esperada_total_ars=q2(esperada_total),
        liquidada_total_ars=q2(liquidada_total),
        diferencia_total_ars=q2(diferencia_total),
        receivable_vencido_ars=q2(receivable_total),
        por_aseguradora={
            k: {
                "esperada_ars": q2(v["esperada"]),
                "liquidada_ars": q2(v["liquidada"]),
                "diferencia_ars": q2(v["diferencia"]),
            }
            for k, v in por_aseg.items()
        },
        discrepancia_ids=sorted(disc_ids),
        receivable_vencido_ids=sorted(recv_ids),
        hallazgos=hallazgos,
    )
