"""Conversión: lead-to-win and quote-to-bind conversion by ramo/canal/productor.
Proposes coaching/review flags where a segment is below its floor."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core.money import ratio
from nexo_os.core.results import Hallazgo
from nexo_os.data.models import Cotizacion, Lead, LeadEstado

AGENTE = "conversion"
_MIN_SEGMENT = 8  # minimum closed leads in a segment before flagging conversion


@dataclass(frozen=True)
class ConversionResult:
    leads_ganados: int
    leads_perdidos: int
    leads_cerrados: int
    lead_to_win_rate: Decimal | None
    quotes_bound: int
    quotes_total: int
    quote_to_bind_rate: Decimal | None
    por_segmento: dict[str, dict]  # "dim:value" -> {ganados, cerrados, rate}
    hallazgos: list[Hallazgo] = field(default_factory=list)


def compute(
    leads: list[Lead], cotizaciones: list[Cotizacion], thresholds: Thresholds
) -> ConversionResult:
    ganados = sum(1 for ld in leads if ld.estado is LeadEstado.ganado)
    perdidos = sum(1 for ld in leads if ld.estado is LeadEstado.perdido)
    cerrados = ganados + perdidos
    lead_to_win = ratio(Decimal(ganados), Decimal(cerrados))

    quotes_bound = sum(1 for c in cotizaciones if c.poliza_id is not None)
    quotes_total = len(cotizaciones)
    quote_to_bind = ratio(Decimal(quotes_bound), Decimal(quotes_total))

    # per-segment lead-to-win, only over closed leads
    seg: dict[str, dict] = {}
    for ld in leads:
        if ld.estado not in (LeadEstado.ganado, LeadEstado.perdido):
            continue
        for dim, value in (
            ("ramo", ld.ramo.value),
            ("canal", ld.canal_origen.value),
            ("productor", ld.productor_id),
        ):
            key = f"{dim}:{value}"
            s = seg.setdefault(key, {"ganados": 0, "cerrados": 0})
            s["cerrados"] += 1
            if ld.estado is LeadEstado.ganado:
                s["ganados"] += 1

    floor = Decimal(str(thresholds.conversion_floor_lead_to_win))
    por_segmento: dict[str, dict] = {}
    hallazgos: list[Hallazgo] = []
    for key, s in seg.items():
        rate = ratio(Decimal(s["ganados"]), Decimal(s["cerrados"]))
        por_segmento[key] = {"ganados": s["ganados"], "cerrados": s["cerrados"], "rate": rate}
        if s["cerrados"] >= _MIN_SEGMENT and rate is not None and rate < floor:
            hallazgos.append(
                Hallazgo(
                    agente=AGENTE,
                    tipo_accion="revisar_conversion_segmento",
                    entidad_tipo="segmento",
                    entidad_id=key,
                    monto_en_juego_ars=None,
                    urgencia_dias=None,
                    numeros={
                        "segmento": key,
                        "ganados": s["ganados"],
                        "cerrados": s["cerrados"],
                        "tasa": str(rate),
                        "piso": str(floor),
                    },
                    completitud=1.0,
                    senial=float(1 - (rate / floor)) if floor else 0.5,
                )
            )

    return ConversionResult(
        leads_ganados=ganados,
        leads_perdidos=perdidos,
        leads_cerrados=cerrados,
        lead_to_win_rate=lead_to_win,
        quotes_bound=quotes_bound,
        quotes_total=quotes_total,
        quote_to_bind_rate=quote_to_bind,
        por_segmento=por_segmento,
        hallazgos=hallazgos,
    )
