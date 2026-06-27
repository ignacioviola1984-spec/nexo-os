"""Reliability layer: deterministic cross-checks between agents. On a mismatch beyond
tolerance, a warning is raised and surfaced (the run is marked con_warnings) — never
silently averaged or hidden.

Reconciliations that must hold by construction:
  * cobranza overdue total  == morosidad overdue total
  * cartera expected commission == sum of current-period comisiones (esperada)
  * profitability net commission (sum over ramos) == cartera expected commission
"""

from __future__ import annotations

from decimal import Decimal

from nexo_os.core.money import dsum, q2
from nexo_os.state import NexoContext

SEV_ALTA = "ALTA"


def reconcile(ctx: NexoContext) -> list[tuple[str, str]]:
    tol = Decimal(str(ctx.thresholds.reconciliation_tolerance_ars))
    warnings: list[tuple[str, str]] = []

    cob = ctx.get_result("cobranza")
    mor = ctx.get_result("morosidad")
    if cob is not None and mor is not None:
        diff = abs(cob.total_vencido_ars - mor.total_vencido_ars)
        if diff > tol:
            warnings.append(
                (
                    SEV_ALTA,
                    f"Cobranza vs morosidad: total vencido difiere en ARS {diff} "
                    f"({cob.total_vencido_ars} vs {mor.total_vencido_ars}).",
                )
            )

    car = ctx.get_result("cartera")
    if car is not None:
        current = q2(dsum(c.comision_esperada_ars for c in ctx.comisiones_periodo_actual))
        diff = abs(car.comision_esperada_ars - current)
        if diff > tol:
            warnings.append(
                (
                    SEV_ALTA,
                    f"Cartera vs comisiones (período actual): comisión esperada difiere en "
                    f"ARS {diff} ({car.comision_esperada_ars} vs {current}).",
                )
            )

    prof = ctx.get_result("profitability")
    if prof is not None and car is not None:
        prof_total = q2(dsum(r["comision_neta_ars"] for r in prof.por_ramo.values()))
        diff = abs(prof_total - car.comision_esperada_ars)
        if diff > tol:
            warnings.append(
                (
                    SEV_ALTA,
                    f"Rentabilidad vs cartera: comisión neta total difiere en ARS {diff} "
                    f"({prof_total} vs {car.comision_esperada_ars}).",
                )
            )

    return warnings
