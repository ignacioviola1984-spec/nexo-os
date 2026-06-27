"""Shared core result types.

`Hallazgo` (finding) is the deterministic bridge between core and the agents: core
produces findings with the numbers, an amount at stake, an urgency, and the data
completeness/signal strength used to derive confidence. The agent turns a Hallazgo
into a proposed `Accion` with a deterministic confidence and priority — the model
never touches any of these numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


class InsufficientData(Exception):
    """Raised when a metric cannot be computed from the data. Fail closed — never
    substitute a default that could read as real."""


@dataclass(frozen=True)
class Hallazgo:
    """A deterministic finding an agent may propose as an action."""

    agente: str
    tipo_accion: str
    entidad_tipo: str  # cliente | poliza | lead | cotizacion | comision | ramo | aseguradora
    entidad_id: str
    #: amount at stake in ARS, or None when the finding has no natural amount
    #: (SLA breaches, data-quality flags, concentration reviews). Never defaulted.
    monto_en_juego_ars: Decimal | None
    #: urgency in days (e.g. days overdue, days-to-expiry). None when not time-bound.
    urgencia_dias: int | None
    #: the deterministic numbers behind the finding (becomes rationale_json).
    numeros: dict = field(default_factory=dict)
    #: data completeness 0..1 (drives confidence).
    completitud: float = 1.0
    #: signal strength 0..1 (drives confidence).
    senial: float = 1.0
