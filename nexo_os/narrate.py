"""Narration: the only place the model is used, and only for Spanish prose. The model
must not introduce or alter a figure — numbers come from the deterministic rationale.
A grounding check (grounding.py) verifies every number in the prose; if the model
fails it (or no API key is set), we fall back to the deterministic, grounded text.
"""

from __future__ import annotations

import json

from nexo_os.config import Settings, get_settings
from nexo_os.data.models import Accion
from nexo_os.grounding import is_grounded
from nexo_os.i18n import fmt_ars
from nexo_os.logging_setup import get_logger

log = get_logger("narrate")


def _ratio_es(value: str | None) -> str:
    return (value or "").replace(".", ",")


def _ars(value: str | None) -> str:
    from decimal import Decimal, InvalidOperation

    if value is None:
        return "sin monto"
    try:
        return fmt_ars(Decimal(value))
    except InvalidOperation:
        return value


def deterministic_facts(accion: Accion) -> str:
    """Grounded Spanish text built strictly from the action's rationale numbers."""
    payload = json.loads(accion.rationale_json)
    n = payload.get("numeros", {})
    t = accion.tipo_accion

    if t == "gestionar_cobro":
        return (
            f"Cuota {n.get('cuota_id')} de la póliza {n.get('poliza_id')} con "
            f"{n.get('dias_mora')} días de mora (tramo {n.get('bucket')}); "
            f"monto vencido {_ars(n.get('monto_vencido_ars'))}."
        )
    if t == "escalar_segmento_mora":
        return (
            f"Tramo de mora {n.get('bucket')}: {n.get('count')} cuotas por "
            f"{_ars(n.get('ars'))}. Total vencido {_ars(n.get('total_vencido_ars'))}."
        )
    if t == "gestionar_renovacion":
        return (
            f"Póliza {n.get('poliza_id')} vence en {n.get('dias_a_vencimiento')} días; "
            f"prima {_ars(n.get('prima_ars'))}."
        )
    if t == "retener_cliente":
        return (
            f"Cliente {n.get('cliente_id')} con comisión en riesgo "
            f"{_ars(n.get('comision_en_riesgo_ars'))} (señales: {n.get('señales')})."
        )
    if t == "reclamar_diferencia_comision":
        return (
            f"Comisión {n.get('comision_id')} (aseguradora {n.get('aseguradora_id')}, "
            f"período {n.get('periodo')}): esperada {_ars(n.get('esperada_ars'))}, "
            f"liquidada {_ars(n.get('liquidada_ars'))}, diferencia {_ars(n.get('diferencia_ars'))}."
        )
    if t == "gestionar_comision_por_cobrar":
        return (
            f"Comisión {n.get('comision_id')} por cobrar a {n.get('aseguradora_id')}: "
            f"{_ars(n.get('pendiente_ars'))} con {n.get('dias_aging')} días de antigüedad."
        )
    if t == "revisar_segmento_no_rentable":
        return (
            f"Ramo {n.get('ramo')}: siniestros pagados {_ars(n.get('siniestros_pagados_ars'))} "
            f"sobre prima {_ars(n.get('prima_ars'))} (ratio {_ratio_es(n.get('loss_ratio'))})."
        )
    if t == "revisar_concentracion_aseguradora":
        return (
            f"Concentración en {n.get('aseguradora_top')}: HHI {_ratio_es(n.get('hhi_aseguradora'))} "
            f"(umbral {_ratio_es(n.get('umbral'))})."
        )
    if t == "avanzar_oportunidad":
        return (
            f"Oportunidad {n.get('lead_id')} en etapa {n.get('etapa')} sin avanzar hace "
            f"{n.get('dias_en_etapa')} días; valor estimado {_ars(n.get('valor_estimado_ars'))}."
        )
    if t == "revisar_conversion_segmento":
        return (
            f"Segmento {n.get('segmento')}: {n.get('ganados')} ganados sobre "
            f"{n.get('cerrados')} cerrados (tasa {_ratio_es(n.get('tasa'))})."
        )
    if t == "contactar_lead_sla":
        return (
            f"Lead {n.get('lead_id')} en estado {n.get('estado')} sin movimiento hace "
            f"{n.get('dias_sin_movimiento')} días (SLA {n.get('sla_dias')})."
        )
    if t == "presentar_cotizacion":
        return (
            f"Cotización {n.get('cotizacion_id')} emitida sin presentar hace "
            f"{n.get('dias_sin_presentar')} días."
        )
    if t == "cotizar_lead":
        return f"Lead {n.get('lead_id')} ({n.get('estado')}) sin cotización en plazo."
    # generic fallback
    return f"Acción {t} sobre {accion.entidad_tipo} {accion.entidad_id}."


_SYSTEM = (
    "Sos analista de una corredora de seguros en Argentina. Escribís en español "
    "rioplatense, profesional y conciso. Regla absoluta: NUNCA inventes, estimes, "
    "redondees ni modifiques cifras. Usá EXACTAMENTE los números provistos y no "
    "introduzcas ningún número nuevo. Devolvé 1 o 2 oraciones de recomendación."
)


def _model_narrate(accion: Accion, facts: str, settings: Settings) -> str | None:
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model=settings.model,
            max_tokens=settings.model_max_tokens,
            system=_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Hechos deterministas (no agregues otros números):\n{facts}\n\n"
                        "Redactá una recomendación breve para el equipo."
                    ),
                }
            ],
        )
        parts = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
        return "".join(parts).strip() or None
    except Exception as exc:  # network/key/quota -> fall back to grounded text
        log.warning("narrate.model_error", error=str(exc), accion_id=accion.accion_id)
        return None


def narrate(accion: Accion, settings: Settings | None = None, allow_model: bool = True) -> str:
    settings = settings or get_settings()
    facts = deterministic_facts(accion)
    if not allow_model or not settings.anthropic_api_key:
        return facts
    prose = _model_narrate(accion, facts, settings)
    if prose is None:
        return facts
    payload = json.loads(accion.rationale_json)
    if is_grounded(prose, payload):
        return prose
    log.warning("narrate.grounding_failed", accion_id=accion.accion_id)
    return facts
