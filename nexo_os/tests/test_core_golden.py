"""Golden tests: core metrics reproduce the planted ground truth exactly. Requires
`python -m nexo_os seed`. Ground-truth figures were accumulated by the generator —
an implementation path independent of core — so agreement here checks both sides.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

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
from nexo_os.data.factory import get_repository
from nexo_os.data.ground_truth import ground_truth_path, load_ground_truth

pytestmark = pytest.mark.skipif(
    not ground_truth_path().exists(), reason="run `python -m nexo_os seed` first"
)
T = Thresholds()


@pytest.fixture(scope="module")
def data():
    repo = get_repository()
    return {
        "repo": repo,
        "snap": repo.snapshot_fecha,
        "gt": load_ground_truth(),
        "polizas": repo.get_polizas(),
        "cuotas": repo.get_cuotas(),
        "comisiones": repo.get_comisiones(),
        "leads": repo.get_leads(),
        "cotizaciones": repo.get_cotizaciones(),
        "siniestros": repo.get_siniestros(),
        "interacciones": repo.get_interacciones(),
    }


def test_cartera_golden(data) -> None:
    r = cartera.compute(data["polizas"], T)
    gt = data["gt"]["cartera"]
    assert r.polizas_vigentes == gt["polizas_vigentes"]
    assert r.prima_total_ars == Decimal(gt["prima_total_ars"])
    assert r.comision_esperada_ars == Decimal(gt["comision_esperada_ars"])


def test_morosidad_golden(data) -> None:
    r = morosidad.compute(data["cuotas"], data["snap"], T)
    gt = data["gt"]["morosidad"]
    assert r.total_vencido_count == gt["total_count"]
    assert r.total_vencido_ars == Decimal(gt["total_vencido_ars"])
    assert r.cuota_ids == sorted(gt["cuota_ids"])
    for label, b in gt["buckets"].items():
        assert r.por_bucket[label]["count"] == b["count"]
        assert r.por_bucket[label]["ars"] == Decimal(b["ars"])


def test_cobranza_reconciles_with_morosidad(data) -> None:
    cob = cobranza.compute(data["cuotas"], data["polizas"], data["snap"], T)
    assert cob.total_vencido_ars == Decimal(data["gt"]["cobranza"]["total_recuperable_ars"])
    assert cob.total_vencido_count == data["gt"]["cobranza"]["items_count"]


def test_comisiones_golden(data) -> None:
    r = comisiones.compute(data["comisiones"], data["snap"], T)
    gt = data["gt"]["comisiones"]
    assert r.discrepancia_ids == sorted(gt["discrepancia_ids"])
    assert r.diferencia_total_ars == Decimal(gt["total_diferencia_ars"])
    assert r.receivable_vencido_ids == sorted(gt["receivable_aged_ids"])
    assert r.receivable_vencido_ars == Decimal(gt["receivable_aged_ars"])


def test_profitability_golden(data) -> None:
    r = profitability.compute(data["polizas"], data["siniestros"], T)
    gt = data["gt"]["profitability"]
    assert r.por_ramo["caucion"]["loss_ratio"] == Decimal(gt["caucion_loss_ratio"])
    assert r.por_ramo["caucion"]["prima_ars"] == Decimal(gt["caucion_premium_ars"])
    assert r.por_ramo["caucion"]["siniestros_pagados_ars"] == Decimal(gt["caucion_claims_paid_ars"])
    assert r.ramos_no_rentables == gt["unprofitable_ramos"]


def test_retention_golden(data) -> None:
    r = retention.compute(data["polizas"], data["cuotas"], data["interacciones"], data["snap"], T)
    gt = data["gt"]["retention"]
    assert r.at_risk_client_ids == sorted(gt["at_risk_client_ids"])
    assert r.comision_en_riesgo_ars == Decimal(gt["comision_en_riesgo_ars"])


def test_renewals_golden(data) -> None:
    r = renewals.compute(data["polizas"], data["siniestros"], data["cuotas"], data["snap"], T)
    gt = data["gt"]["renewals"]
    assert r.expira_30_count == gt["expira_30_count"]
    assert r.expira_60_count == gt["expira_60_count"]
    assert r.expira_90_count == gt["expira_90_count"]
    assert r.expira_total_90d_count == gt["expira_total_90d_count"]
    assert r.prima_en_riesgo_90d_ars == Decimal(gt["prima_en_riesgo_90d_ars"])
    assert r.at_risk_ids == sorted(gt["at_risk_ids"])


def test_conversion_golden(data) -> None:
    r = conversion.compute(data["leads"], data["cotizaciones"], T)
    gt = data["gt"]["conversion"]
    assert r.leads_ganados == gt["leads_ganados"]
    assert r.leads_perdidos == gt["leads_perdidos"]
    assert r.quotes_bound == gt["quotes_bound"]


def test_pipeline_golden(data) -> None:
    r = pipeline.compute(data["leads"], data["cotizaciones"], data["snap"], T)
    aging_ids = sorted(h.entidad_id for h in r.hallazgos)
    assert aging_ids == sorted(data["gt"]["pipeline"]["aging_ids"])


def test_leads_control_golden(data) -> None:
    r = leads_control.compute(data["leads"], data["cotizaciones"], data["snap"], T)
    gt = data["gt"]["leads_control"]
    assert r.sla_breach_ids == sorted(gt["sla_breach_ids"])
    assert r.quotes_no_presentadas_ids == sorted(gt["quotes_no_presentadas_ids"])
