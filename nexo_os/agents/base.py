"""The agent contract.

Each agent implements `compute(ctx)` (deterministic figures via core — no model).
`propose` (shared here) turns each Hallazgo into a proposed Accion with a
DETERMINISTIC confidence and priority — the model never touches these numbers.
`narrate` (Phase 5) is the only place the model is used, and only for Spanish prose.

Confidence and priority are documented, pure functions of the data:
  * confidence = 0.5*data_completeness + 0.5*signal_strength, clamped to [0,1].
  * priority routes by amount at stake when present, else by urgency in days. A
    missing amount stays None and routes by urgency alone — never defaulted.
"""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod

from nexo_os.clock import now
from nexo_os.config import Thresholds
from nexo_os.core.results import Hallazgo
from nexo_os.data.models import Accion, AccionEstado, Prioridad
from nexo_os.state import NexoContext


def confidence(h: Hallazgo) -> float:
    raw = 0.5 * h.completitud + 0.5 * h.senial
    return round(min(1.0, max(0.0, raw)), 4)


def priority(monto_en_juego_ars, urgencia_dias: int | None, t: Thresholds) -> Prioridad:
    """Deterministic. Amount-driven when an amount exists; otherwise urgency-only.
    A missing amount is never inferred or defaulted to fill the gap."""
    if monto_en_juego_ars is not None:
        monto = float(monto_en_juego_ars)
        if monto >= t.priority_alta_ars:
            return Prioridad.alta
        if monto >= t.priority_media_ars:
            return Prioridad.media
        return Prioridad.baja
    # urgency-only branch (SLA breaches, data-quality flags, concentration reviews)
    if urgencia_dias is not None:
        if urgencia_dias >= t.priority_alta_urgency_days:
            return Prioridad.alta
        if urgencia_dias >= t.priority_media_urgency_days:
            return Prioridad.media
    return Prioridad.baja


def _rationale_json(h: Hallazgo) -> str:
    payload = {
        "agente": h.agente,
        "tipo_accion": h.tipo_accion,
        "entidad": {"tipo": h.entidad_tipo, "id": h.entidad_id},
        "monto_en_juego_ars": (
            str(h.monto_en_juego_ars) if h.monto_en_juego_ars is not None else None
        ),
        "urgencia_dias": h.urgencia_dias,
        "numeros": h.numeros,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def build_accion(h: Hallazgo, run_id: str, t: Thresholds) -> Accion:
    return Accion(
        accion_id=uuid.uuid4().hex,
        agente=h.agente,
        tipo_accion=h.tipo_accion,
        entidad_tipo=h.entidad_tipo,
        entidad_id=h.entidad_id,
        prioridad=priority(h.monto_en_juego_ars, h.urgencia_dias, t),
        confianza=confidence(h),
        monto_en_juego_ars=h.monto_en_juego_ars,
        rationale_json=_rationale_json(h),
        mensaje_es="",  # filled by narrate (Phase 5); empty = deterministic-only
        estado=AccionEstado.propuesta,
        creada_en=now(),
        resuelta_en=None,
        resuelta_por=None,
        nota_revisor=None,
        run_id=run_id,
    )


class Agent(ABC):
    """Base agent. Subclasses set `id` and implement `compute`."""

    id: str

    @abstractmethod
    def compute(self, ctx: NexoContext) -> object:
        """Deterministic figures via core. No model call."""

    def hallazgos(self, result: object) -> list[Hallazgo]:
        return list(getattr(result, "hallazgos", []))

    def propose(self, ctx: NexoContext, result: object) -> list[Accion]:
        """Turn deterministic findings into proposed actions. No model call."""
        return [build_accion(h, ctx.run_id, ctx.thresholds) for h in self.hallazgos(result)]
