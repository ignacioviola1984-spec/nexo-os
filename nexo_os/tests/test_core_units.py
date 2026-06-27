"""Core unit tests with hand-verified expected values and edge cases."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core import (
    cartera,
    cobranza,
    comisiones,
    conversion,
    leads_control,
    morosidad,
    pipeline,
    profitability,
    renewals,
    retention,
)
from nexo_os.core.aging import bucket_mora, is_overdue
from nexo_os.core.money import ZERO, q2, ratio
from nexo_os.tests import factories as f

T = Thresholds()
SNAP = date(2026, 6, 30)


# --- money / aging --------------------------------------------------------------


def test_money_ratio_fails_closed_on_zero() -> None:
    assert ratio(Decimal("5"), ZERO) is None
    assert ratio(Decimal("6"), Decimal("4")) == Decimal("1.5")


def test_q2_rounds_half_up() -> None:
    assert q2("1.005") == Decimal("1.01")


def test_aging_buckets() -> None:
    assert bucket_mora(0, T.mora) == "0"
    assert bucket_mora(30, T.mora) == "1-30"
    assert bucket_mora(31, T.mora) == "31-60"
    assert bucket_mora(90, T.mora) == "61-90"
    assert bucket_mora(91, T.mora) == "90+"


def test_is_overdue_ignores_paid() -> None:
    paid = f.cuota(estado="pagada", venc=date(2026, 1, 1), pagado="10000.00")
    assert not is_overdue(paid, SNAP)
    due = f.cuota(estado="vencida", venc=date(2026, 5, 1))
    assert is_overdue(due, SNAP)


# --- morosidad / cobranza ------------------------------------------------------


def test_morosidad_buckets_and_total() -> None:
    cuotas = [
        f.cuota(cuota_id="a", estado="vencida", venc=date(2026, 6, 20), monto="1000.00"),  # 10d
        f.cuota(cuota_id="b", estado="vencida", venc=date(2026, 5, 20), monto="2000.00"),  # 41d
        f.cuota(cuota_id="c", estado="vencida", venc=date(2026, 1, 1), monto="3000.00"),  # 180d
        f.cuota(cuota_id="d", estado="pendiente", venc=date(2026, 8, 1), monto="9000.00"),  # future
    ]
    r = morosidad.compute(cuotas, SNAP, T)
    assert r.total_vencido_count == 3
    assert r.total_vencido_ars == Decimal("6000.00")
    assert r.por_bucket["1-30"]["count"] == 1
    assert r.por_bucket["31-60"]["count"] == 1
    assert r.por_bucket["90+"]["count"] == 1
    assert r.por_bucket["61-90"]["count"] == 0


def test_cobranza_total_ties_to_morosidad_and_orders_by_score() -> None:
    cuotas = [
        f.cuota(
            cuota_id="a", poliza_id="P1", estado="vencida", venc=date(2026, 6, 20), monto="1000.00"
        ),
        f.cuota(
            cuota_id="b", poliza_id="P2", estado="vencida", venc=date(2026, 1, 1), monto="5000.00"
        ),
    ]
    polizas = [f.poliza(poliza_id="P1", cliente_id="C1"), f.poliza(poliza_id="P2", cliente_id="C2")]
    cob = cobranza.compute(cuotas, polizas, SNAP, T)
    mor = morosidad.compute(cuotas, SNAP, T)
    assert cob.total_vencido_ars == mor.total_vencido_ars == Decimal("6000.00")
    # larger + older should rank first
    assert cob.hallazgos[0].numeros["cuota_id"] == "b"


# --- cartera -------------------------------------------------------------------


def test_cartera_premium_commission_and_hhi() -> None:
    polizas = [
        f.poliza(poliza_id="P1", aseguradora_id="A", prima="60000.00", comision_pct="0.100000"),
        f.poliza(poliza_id="P2", aseguradora_id="B", prima="40000.00", comision_pct="0.100000"),
    ]
    r = cartera.compute(polizas, T)
    assert r.prima_total_ars == Decimal("100000.00")
    assert r.comision_esperada_ars == Decimal("10000.00")
    assert r.hhi_aseguradora == Decimal("0.52")  # 0.6^2 + 0.4^2


def test_cartera_growth_is_none_without_history() -> None:
    r = cartera.compute([f.poliza()], T)
    assert r.crecimiento_mom is None and r.crecimiento_yoy is None


# --- comisiones ----------------------------------------------------------------


def test_comisiones_period_end() -> None:
    assert comisiones.period_end("2026-02") == date(2026, 2, 28)


def test_comisiones_discrepancy_and_aged_receivable() -> None:
    rows = [
        f.comision(comision_id="ok", estado="liquidada", esperada="1000.00", liquidada="1000.00"),
        f.comision(
            comision_id="dif",
            estado="con_diferencia",
            periodo="2026-05",
            esperada="1000.00",
            liquidada="700.00",
            diferencia="300.00",
        ),
        f.comision(
            comision_id="recv",
            estado="esperada",
            periodo="2026-04",
            esperada="500.00",
            liquidada=None,
            diferencia="500.00",
            fecha_liq=None,
        ),
    ]
    r = comisiones.compute(rows, SNAP, T)
    assert r.discrepancia_ids == ["dif"]
    assert r.diferencia_total_ars == Decimal("300.00")
    assert r.receivable_vencido_ids == ["recv"]
    assert r.receivable_vencido_ars == Decimal("500.00")


# --- profitability -------------------------------------------------------------


def test_profitability_loss_ratio() -> None:
    polizas = [f.poliza(poliza_id="P1", ramo="caucion", prima="100000.00")]
    sin = [f.siniestro(poliza_id="P1", estado="pagado", pagado="85000.00")]
    r = profitability.compute(polizas, sin, T)
    assert r.por_ramo["caucion"]["loss_ratio"] == Decimal("0.85")
    assert r.ramos_no_rentables == ["caucion"]


# --- retention -----------------------------------------------------------------


def test_retention_inactivity_and_lapse() -> None:
    polizas = [
        f.poliza(poliza_id="P1", cliente_id="C1", prima="100000.00", comision_pct="0.100000"),
        f.poliza(poliza_id="P2", cliente_id="C2", prima="200000.00", comision_pct="0.100000"),
        f.poliza(poliza_id="P3", cliente_id="C3", prima="50000.00", comision_pct="0.100000"),
    ]
    cuotas = [f.cuota(poliza_id="C2P", estado="vencida", venc=date(2026, 1, 1))]
    cuotas[0] = f.cuota(cuota_id="x", poliza_id="P2", estado="vencida", venc=date(2026, 1, 1))
    inter = [
        f.interaccion(entidad_id="C1", fecha=date(2025, 1, 1)),  # inactive (>180d)
        f.interaccion(entidad_id="C2", fecha=date(2026, 6, 1)),  # recent, but lapse via P2
        f.interaccion(entidad_id="C3", fecha=date(2026, 6, 1)),  # healthy
    ]
    r = retention.compute(polizas, cuotas, inter, SNAP, T)
    assert r.at_risk_client_ids == ["C1", "C2"]
    assert r.comision_en_riesgo_ars == Decimal("30000.00")  # 10000 + 20000


# --- renewals ------------------------------------------------------------------


def test_renewals_windows_and_at_risk() -> None:
    polizas = [
        f.poliza(poliza_id="E30", fin=date(2026, 7, 20), prima="100000.00"),  # 20d
        f.poliza(poliza_id="E60", fin=date(2026, 8, 15), prima="100000.00"),  # 46d
        f.poliza(poliza_id="FAR", fin=date(2027, 1, 1), prima="100000.00"),  # >90d
    ]
    sin = [f.siniestro(poliza_id="E30", estado="pagado", pagado="10000.00")]
    r = renewals.compute(polizas, sin, [], SNAP, T)
    assert r.expira_30_count == 1 and r.expira_60_count == 1 and r.expira_90_count == 0
    assert r.expira_total_90d_count == 2
    assert r.prima_en_riesgo_90d_ars == Decimal("200000.00")
    assert r.at_risk_ids == ["E30"]


# --- conversion ----------------------------------------------------------------


def test_conversion_rates() -> None:
    leads = [
        f.lead(lead_id="g1", estado="ganado"),
        f.lead(lead_id="g2", estado="ganado"),
        f.lead(lead_id="p1", estado="perdido"),
        f.lead(lead_id="open", estado="nuevo"),
    ]
    quotes = [
        f.cotizacion(cotizacion_id="q1", lead_id="g1", estado="aceptada", poliza_id="POLX"),
        f.cotizacion(cotizacion_id="q2", lead_id="p1", estado="rechazada"),
    ]
    r = conversion.compute(leads, quotes, T)
    assert r.leads_ganados == 2 and r.leads_perdidos == 1
    assert r.lead_to_win_rate == ratio(Decimal(2), Decimal(3))
    assert r.quotes_bound == 1 and r.quotes_total == 2


# --- pipeline ------------------------------------------------------------------


def test_pipeline_forecast_and_aging() -> None:
    leads = [
        f.lead(lead_id="L1", estado="cotizado", ultimo=date(2026, 6, 1)),  # 29d aging
        f.lead(lead_id="L2", estado="presentado", ultimo=date(2026, 6, 29)),  # fresh
    ]
    quotes = [
        f.cotizacion(cotizacion_id="q1", lead_id="L1", prima="100000.00"),
        f.cotizacion(cotizacion_id="q2", lead_id="L2", prima="200000.00"),
    ]
    r = pipeline.compute(leads, quotes, SNAP, T)
    assert r.open_count == 2
    assert r.open_value_ars == Decimal("300000.00")
    # forecast = 100000*0.35 + 200000*0.60 = 35000 + 120000
    assert r.forecast_ponderado_ars == Decimal("155000.00")
    aging_ids = [h.entidad_id for h in r.hallazgos]
    assert aging_ids == ["L1"]


# --- leads_control -------------------------------------------------------------


def test_leads_control_sla_np_and_no_quote_dedup() -> None:
    leads = [
        f.lead(
            lead_id="sla", estado="contactado", ultimo=date(2026, 6, 1), ingreso=date(2026, 4, 1)
        ),
        f.lead(
            lead_id="fresh", estado="nuevo", ultimo=date(2026, 6, 29), ingreso=date(2026, 6, 28)
        ),
    ]
    quotes = [
        f.cotizacion(cotizacion_id="npq", lead_id="x", estado="emitida", fecha=date(2026, 6, 1)),
    ]
    r = leads_control.compute(leads, quotes, SNAP, T)
    assert r.sla_breach_ids == ["sla"]
    assert r.quotes_no_presentadas_ids == ["npq"]
    # 'sla' lead has no quote but is already SLA-flagged -> not double-counted
    assert r.leads_sin_cotizacion_count == 0
