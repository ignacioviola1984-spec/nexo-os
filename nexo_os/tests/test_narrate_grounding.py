"""Phase 5: the determinism wall. Deterministic facts are always grounded; invented
numbers are rejected; narrate falls back to grounded text without an API key."""

from __future__ import annotations

import json
from decimal import Decimal

from nexo_os.agents.base import build_accion
from nexo_os.config import Settings, Thresholds
from nexo_os.core.results import Hallazgo
from nexo_os.grounding import is_grounded
from nexo_os.narrate import deterministic_facts, narrate

T = Thresholds()


def _accion(tipo="gestionar_cobro", numeros=None, monto="123456.78"):
    h = Hallazgo(
        agente="cobranza",
        tipo_accion=tipo,
        entidad_tipo="cliente",
        entidad_id="C1",
        monto_en_juego_ars=Decimal(monto) if monto else None,
        urgencia_dias=95,
        numeros=numeros
        or {
            "cuota_id": "CUO-1",
            "poliza_id": "POL-1",
            "monto_vencido_ars": "123456.78",
            "dias_mora": 95,
            "bucket": "90+",
        },
    )
    return build_accion(h, run_id="R", t=T)


def test_deterministic_facts_are_grounded() -> None:
    a = _accion()
    facts = deterministic_facts(a)
    payload = json.loads(a.rationale_json)
    assert is_grounded(facts, payload)
    assert "123.456,78" in facts  # Argentine formatting of the rationale amount


def test_grounding_rejects_invented_number() -> None:
    a = _accion()
    payload = json.loads(a.rationale_json)
    bad = deterministic_facts(a) + " Además, recuperaríamos ARS 999.999.999."
    assert not is_grounded(bad, payload)


def test_grounding_accepts_plain_and_argentine_formats() -> None:
    payload = {"numeros": {"monto": "12000.00", "dias": 95}}
    assert is_grounded("Son ARS 12.000,00 a 95 días.", payload)
    assert is_grounded("Son 12000 pesos.", payload)
    assert not is_grounded("Son ARS 12.500,00.", payload)


def test_narrate_without_key_returns_grounded_facts() -> None:
    a = _accion()
    s = Settings(ANTHROPIC_API_KEY=None)
    out = narrate(a, settings=s, allow_model=True)
    assert out == deterministic_facts(a)


def test_ratio_facts_grounded() -> None:
    a = _accion(
        tipo="revisar_segmento_no_rentable",
        numeros={
            "ramo": "caucion",
            "prima_ars": "1000000.00",
            "siniestros_pagados_ars": "850000.00",
            "loss_ratio": "0.85",
            "umbral": "0.70",
        },
        monto="850000.00",
    )
    facts = deterministic_facts(a)
    assert is_grounded(facts, json.loads(a.rationale_json))
    assert "0,85" in facts  # ratio shown as decimal, not derived percentage
