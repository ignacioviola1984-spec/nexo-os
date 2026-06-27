"""Cartera (portfolio): policies in force, premium, expected commission, mix and
concentration. Mostly informational; proposes over-concentration reviews."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core.money import ZERO, dsum, q2, ratio
from nexo_os.core.results import Hallazgo
from nexo_os.data.models import Poliza, PolizaEstado

AGENTE = "cartera"


@dataclass(frozen=True)
class CarteraResult:
    polizas_vigentes: int
    prima_total_ars: Decimal
    comision_esperada_ars: Decimal
    mix_por_ramo: dict[str, dict]
    mix_por_aseguradora: dict[str, dict]
    hhi_aseguradora: Decimal | None
    hhi_cliente: Decimal | None
    # growth requires prior snapshots, which this build does not retain -> None
    crecimiento_mom: Decimal | None
    crecimiento_yoy: Decimal | None
    hallazgos: list[Hallazgo] = field(default_factory=list)


def _hhi(premium_by_group: dict[str, Decimal], total: Decimal) -> Decimal | None:
    if total == ZERO:
        return None
    acc = ZERO
    for prem in premium_by_group.values():
        share = prem / total
        acc += share * share
    return acc


def compute(polizas: list[Poliza], thresholds: Thresholds) -> CarteraResult:
    vigentes = [p for p in polizas if p.estado is PolizaEstado.vigente]
    prima_total = dsum(p.prima_ars for p in vigentes)
    comision_total = q2(dsum(p.prima_ars * p.comision_pct for p in vigentes))

    mix_ramo: dict[str, dict] = {}
    prem_by_ramo: dict[str, Decimal] = {}
    for p in vigentes:
        r = p.ramo.value
        m = mix_ramo.setdefault(r, {"count": 0, "prima_ars": ZERO})
        m["count"] += 1
        m["prima_ars"] += p.prima_ars
        prem_by_ramo[r] = prem_by_ramo.get(r, ZERO) + p.prima_ars

    mix_aseg: dict[str, dict] = {}
    prem_by_aseg: dict[str, Decimal] = {}
    for p in vigentes:
        a = p.aseguradora_id
        m = mix_aseg.setdefault(a, {"count": 0, "prima_ars": ZERO})
        m["count"] += 1
        m["prima_ars"] += p.prima_ars
        prem_by_aseg[a] = prem_by_aseg.get(a, ZERO) + p.prima_ars

    prem_by_cliente: dict[str, Decimal] = {}
    for p in vigentes:
        prem_by_cliente[p.cliente_id] = prem_by_cliente.get(p.cliente_id, ZERO) + p.prima_ars

    hhi_aseg = _hhi(prem_by_aseg, prima_total)
    hhi_cli = _hhi(prem_by_cliente, prima_total)

    hallazgos: list[Hallazgo] = []
    if hhi_aseg is not None and hhi_aseg > Decimal(str(thresholds.hhi_concentration_alert)):
        # flag the most concentrated insurer
        top_aseg = max(prem_by_aseg, key=lambda k: prem_by_aseg[k])
        share = ratio(prem_by_aseg[top_aseg], prima_total)
        hallazgos.append(
            Hallazgo(
                agente=AGENTE,
                tipo_accion="revisar_concentracion_aseguradora",
                entidad_tipo="aseguradora",
                entidad_id=top_aseg,
                monto_en_juego_ars=None,  # concentration review has no natural amount
                urgencia_dias=None,
                numeros={
                    "hhi_aseguradora": str(hhi_aseg),
                    "umbral": str(thresholds.hhi_concentration_alert),
                    "aseguradora_top": top_aseg,
                    "participacion_top": str(share) if share is not None else None,
                    "prima_top_ars": str(q2(prem_by_aseg[top_aseg])),
                },
                completitud=1.0,
                senial=min(1.0, float(hhi_aseg) / float(thresholds.hhi_concentration_alert)),
            )
        )

    return CarteraResult(
        polizas_vigentes=len(vigentes),
        prima_total_ars=q2(prima_total),
        comision_esperada_ars=comision_total,
        mix_por_ramo={
            k: {"count": v["count"], "prima_ars": q2(v["prima_ars"])} for k, v in mix_ramo.items()
        },
        mix_por_aseguradora={
            k: {"count": v["count"], "prima_ars": q2(v["prima_ars"])} for k, v in mix_aseg.items()
        },
        hhi_aseguradora=hhi_aseg,
        hhi_cliente=hhi_cli,
        crecimiento_mom=None,
        crecimiento_yoy=None,
        hallazgos=hallazgos,
    )
