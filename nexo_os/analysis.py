"""LLM analysis layer — the agents *analyze* via the API.

The deterministic core computes the figures; this layer asks the model to interpret
them: what the numbers show, which patterns/variations matter, and what to prioritize.
The model never invents a figure — every number in its analysis is checked against the
deterministic figures it was given (grounding.py); if it strays (or no API key is set)
we fall back to a deterministic summary. So the model adds judgement, not arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from nexo_os.config import Settings, get_settings
from nexo_os.grounding import is_grounded
from nexo_os.i18n import AGENTES, fmt_ars
from nexo_os.logging_setup import get_logger

log = get_logger("analysis")


@dataclass(frozen=True)
class Analysis:
    text: str
    used_model: bool


# --- collect the deterministic numbers the model is allowed to reference ----------


def _allowed(result) -> dict:
    nums: dict = {}
    for k, v in vars(result).items():
        if k == "hallazgos":
            continue
        if isinstance(v, (int, Decimal)):
            nums[k] = str(v)
    halls = []
    for h in getattr(result, "hallazgos", []):
        halls.append(
            {
                "monto": str(h.monto_en_juego_ars) if h.monto_en_juego_ars is not None else None,
                "urgencia": h.urgencia_dias,
                **{k: str(x) for k, x in h.numeros.items()},
            }
        )
    nums["hallazgos"] = halls
    return nums


def _facts(agent_id: str, result) -> str:
    lines = [f"Agente: {AGENTES.get(agent_id, agent_id)}"]
    for k, v in vars(result).items():
        if k == "hallazgos":
            continue
        if isinstance(v, Decimal):
            lines.append(f"- {k}: {fmt_ars(v)}")
        elif isinstance(v, int):
            lines.append(f"- {k}: {v}")
    halls = getattr(result, "hallazgos", [])
    lines.append(f"- hallazgos detectados: {len(halls)}")
    for h in halls[:8]:
        m = fmt_ars(h.monto_en_juego_ars) if h.monto_en_juego_ars is not None else "sin monto"
        u = f"{h.urgencia_dias} días" if h.urgencia_dias is not None else "sin urgencia"
        lines.append(f"  · {h.tipo_accion} ({h.entidad_tipo} {h.entidad_id}): {m}, {u}")
    return "\n".join(lines)


_SYSTEM = (
    "Sos analista senior de una corredora de seguros en Argentina. Escribís en español "
    "rioplatense, profesional y conciso. Regla absoluta: NUNCA inventes, estimes, "
    "redondees ni derives cifras nuevas; usá EXACTAMENTE los números provistos y, para "
    "proporciones, usá palabras (la mayoría, una parte) en lugar de porcentajes nuevos. "
    "Tu tarea es interpretar, no calcular."
)


def _call_model(user: str, settings: Settings) -> str | None:
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model=settings.model,
            max_tokens=settings.model_max_tokens,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
        return "".join(parts).strip() or None
    except Exception as exc:  # network/key/quota -> deterministic fallback
        log.warning("analysis.model_error", error=str(exc))
        return None


# --- per-agent analysis ----------------------------------------------------------


def _fallback_agent(agent_id: str, result) -> str:
    halls = getattr(result, "hallazgos", [])
    total = sum((h.monto_en_juego_ars or Decimal("0") for h in halls), Decimal("0"))
    nombre = AGENTES.get(agent_id, agent_id)
    if not halls:
        return f"{nombre}: sin hallazgos accionables en esta corrida."
    return (
        f"{nombre}: {len(halls)} hallazgos por {fmt_ars(total)}. "
        "Priorizar los de mayor monto en juego y mayor urgencia."
    )


def analyze_agent(agent_id: str, result, settings: Settings | None = None) -> Analysis:
    settings = settings or get_settings()
    fallback = _fallback_agent(agent_id, result)
    if not settings.anthropic_api_key:
        return Analysis(text=fallback, used_model=False)
    user = (
        "A partir de estas cifras deterministas (no agregues otros números), "
        "escribí un análisis breve para el equipo: (1) qué muestran los datos, "
        "(2) qué patrones o variaciones son relevantes, (3) 2 o 3 recomendaciones "
        f"priorizadas.\n\n{_facts(agent_id, result)}"
    )
    prose = _call_model(user, settings)
    if prose and is_grounded(prose, _allowed(result)):
        return Analysis(text=prose, used_model=True)
    if prose:
        log.warning("analysis.grounding_failed", agent=agent_id)
    return Analysis(text=fallback, used_model=False)


# --- executive synthesis ---------------------------------------------------------


def _exec_facts(results: dict) -> tuple[str, dict]:
    car = results.get("cartera")
    mor = results.get("morosidad")
    com = results.get("comisiones")
    pipe = results.get("pipeline")
    ren = results.get("renewals")
    ret = results.get("retention")
    lines = ["Estado del negocio (cifras deterministas):"]
    allowed: dict = {}

    def add(label: str, value):
        if isinstance(value, Decimal):
            lines.append(f"- {label}: {fmt_ars(value)}")
            allowed[label] = str(value)
        elif isinstance(value, int):
            lines.append(f"- {label}: {value}")
            allowed[label] = str(value)

    if car:
        add("pólizas vigentes", car.polizas_vigentes)
        add("prima total", car.prima_total_ars)
        add("comisión esperada", car.comision_esperada_ars)
    if mor:
        add("mora total", mor.total_vencido_ars)
    if com:
        add("comisiones por cobrar", com.receivable_vencido_ars)
        add("diferencias de comisión", com.diferencia_total_ars)
    if pipe:
        add("pipeline abierto", pipe.open_value_ars)
    if ren:
        add("prima en riesgo (renovaciones 90d)", ren.prima_en_riesgo_90d_ars)
    if ret:
        add("comisión en riesgo (retención)", ret.comision_en_riesgo_ars)
    return "\n".join(lines), allowed


def _fallback_exec(results: dict) -> str:
    car = results.get("cartera")
    mor = results.get("morosidad")
    if not car:
        return "Sin datos suficientes para un resumen ejecutivo."
    return (
        f"Cartera vigente de {car.polizas_vigentes} pólizas por {fmt_ars(car.prima_total_ars)}. "
        f"Mora total {fmt_ars(mor.total_vencido_ars) if mor else 'sin datos'}. "
        "Priorizar cobranza de mayor monto/antigüedad y renovaciones en riesgo."
    )


def executive_summary(results: dict, settings: Settings | None = None) -> Analysis:
    settings = settings or get_settings()
    fallback = _fallback_exec(results)
    if not settings.anthropic_api_key:
        return Analysis(text=fallback, used_model=False)
    facts, allowed = _exec_facts(results)
    user = (
        "Sos el analista que asiste a la dirección de la corredora. Con estas cifras "
        "(no agregues otros números), escribí un resumen ejecutivo de 3 a 5 oraciones: "
        "lectura del estado del negocio, principales focos de atención y prioridades de "
        f"la semana.\n\n{facts}"
    )
    prose = _call_model(user, settings)
    if prose and is_grounded(prose, allowed):
        return Analysis(text=prose, used_model=True)
    if prose:
        log.warning("analysis.exec_grounding_failed")
    return Analysis(text=fallback, used_model=False)
