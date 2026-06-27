"""Read-time aging for installments, computed relative to the run snapshot date.
`dias_mora` and `bucket_mora` are NOT stored columns (see DATA_MODEL.md): computing
them here keeps aging always consistent with the snapshot logic.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from nexo_os.config import MoraBuckets
from nexo_os.data.models import Cuota, CuotaEstado

BUCKET_0 = "0"
BUCKET_1_30 = "1-30"
BUCKET_31_60 = "31-60"
BUCKET_61_90 = "61-90"
BUCKET_90_PLUS = "90+"
ALL_BUCKETS = [BUCKET_1_30, BUCKET_31_60, BUCKET_61_90, BUCKET_90_PLUS]


def dias_mora(fecha_vencimiento: date, snapshot: date) -> int:
    """Days past due relative to the snapshot (negative if not yet due)."""
    return (snapshot - fecha_vencimiento).days


def bucket_mora(dias: int, mora: MoraBuckets) -> str:
    if dias <= 0:
        return BUCKET_0
    if dias <= mora.b1_30:
        return BUCKET_1_30
    if dias <= mora.b31_60:
        return BUCKET_31_60
    if dias <= mora.b61_90:
        return BUCKET_61_90
    return BUCKET_90_PLUS


def outstanding(cuota: Cuota) -> Decimal:
    """Unpaid amount of an installment."""
    return cuota.monto_ars - cuota.monto_pagado_ars


def is_overdue(cuota: Cuota, snapshot: date) -> bool:
    """An installment is overdue if it is not fully paid and its due date has passed."""
    if cuota.estado is CuotaEstado.pagada:
        return False
    return dias_mora(cuota.fecha_vencimiento, snapshot) > 0


def is_unpaid(cuota: Cuota) -> bool:
    return cuota.estado is not CuotaEstado.pagada
