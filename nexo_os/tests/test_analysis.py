"""LLM analysis layer: without an API key it returns a deterministic, grounded
fallback; the allowed-number set is built from the deterministic result."""

from __future__ import annotations

from nexo_os.analysis import _allowed, analyze_agent, executive_summary
from nexo_os.config import Settings
from nexo_os.core import cartera, cobranza
from nexo_os.grounding import is_grounded
from nexo_os.tests import factories as f

OFFLINE = Settings(ANTHROPIC_API_KEY=None)


def _cartera_result():
    return cartera.compute(
        [f.poliza(poliza_id="P1", prima="600000.00"), f.poliza(poliza_id="P2", prima="400000.00")],
        Settings().thresholds,
    )


def test_analyze_agent_fallback_without_key() -> None:
    res = _cartera_result()
    a = analyze_agent("cartera", res, OFFLINE)
    assert a.used_model is False
    assert a.text  # non-empty deterministic summary


def test_executive_summary_fallback_without_key() -> None:
    results = {"cartera": _cartera_result()}
    a = executive_summary(results, OFFLINE)
    assert a.used_model is False
    assert "pólizas" in a.text.lower() or "cartera" in a.text.lower()


def test_allowed_numbers_cover_hallazgo_amounts() -> None:
    from datetime import date

    cuotas = [
        f.cuota(
            cuota_id="x", poliza_id="P1", estado="vencida", venc=date(2026, 1, 1), monto="50000.00"
        )
    ]
    res = cobranza.compute(
        cuotas, [f.poliza(poliza_id="P1")], date(2026, 6, 30), Settings().thresholds
    )
    allowed = _allowed(res)
    # the deterministic total is groundable; an invented figure is not
    assert is_grounded(f"Total vencido {res.total_vencido_ars}.", allowed)
    assert not is_grounded("Total vencido ARS 999.999.999.", allowed)
