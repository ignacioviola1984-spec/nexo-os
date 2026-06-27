"""Money helpers. All currency math is Decimal — never float. Rounding is defined
once here and applied consistently (ARS, 2 decimals, half-up)."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0")
CENT = Decimal("0.01")


def q2(x: Decimal | int | float | str) -> Decimal:
    """Quantize to 2 decimals (ARS), half-up."""
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def dsum(values: Iterable[Decimal]) -> Decimal:
    total = ZERO
    for v in values:
        total += v
    return total


def ratio(num: Decimal, den: Decimal) -> Decimal | None:
    """num/den as a full-precision Decimal, or None when the denominator is zero
    (fail closed — never substitute a default that could read as real)."""
    if den == ZERO:
        return None
    return Decimal(num) / Decimal(den)
