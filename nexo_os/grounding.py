"""Grounding guardrail — the hard wall protecting non-negotiable #1.

Every number that appears in model-written prose must be traceable to the action's
deterministic rationale. A figure passes if it either:
  * equals (numerically) a numeric value in the rationale, or
  * appears as a digit-substring of some rationale string (covers periods like
    '2026-04', ids, day counts embedded in strings).

If the model introduces, alters, or rounds a figure, the prose is rejected and the
caller falls back to the deterministic, grounded text. This module makes no model
calls and is fully deterministic.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_NUM_TOKEN = re.compile(r"\d[\d.,]*")


def _digits(token: str) -> str:
    return re.sub(r"\D", "", token)


def _parse_ar(token: str) -> Decimal | None:
    """Parse a number written in Argentine ('.' thousands, ',' decimal) or plain form."""
    t = token.strip().strip(".,")
    if not t:
        return None
    if "." in t and "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    # '.' only: treat as thousands separator (Spanish prose), unless it is a single
    # group of <=2 trailing decimals (rare in prose). Default: drop dots.
    elif "." in t:
        intpart, _, last = t.rpartition(".")
        if len(last) == 3 and intpart:  # e.g. 12.000 -> thousands
            t = t.replace(".", "")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def _flatten(value: object, decimals: set[Decimal], digit_strings: set[str]) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float, Decimal)):
        decimals.add(Decimal(str(value)))
        digit_strings.add(_digits(str(value)))
        return
    if isinstance(value, str):
        digit_strings.add(_digits(value))
        try:
            decimals.add(Decimal(value))
        except InvalidOperation:
            pass
        return
    if isinstance(value, dict):
        for v in value.values():
            _flatten(v, decimals, digit_strings)
        return
    if isinstance(value, (list, tuple)):
        for v in value:
            _flatten(v, decimals, digit_strings)


def build_allowed(rationale: dict) -> tuple[set[Decimal], set[str]]:
    decimals: set[Decimal] = set()
    digit_strings: set[str] = set()
    _flatten(rationale, decimals, digit_strings)
    digit_strings.discard("")
    return decimals, digit_strings


def is_grounded(text: str, rationale: dict) -> bool:
    decimals, digit_strings = build_allowed(rationale)
    for token in _NUM_TOKEN.findall(text):
        d = _parse_ar(token)
        digits = _digits(token)
        if d is not None and any(d == a for a in decimals):
            continue
        # also accept integer-equality against amounts written without decimals
        if d is not None and any(d == a.to_integral_value() or d == a for a in decimals):
            continue
        if digits and any(digits in s for s in digit_strings):
            continue
        return False
    return True
