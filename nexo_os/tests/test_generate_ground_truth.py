"""Phase 2: verify the generated synthetic store matches its planted ground truth,
cross-checked through the repository (a third path, independent of the generator's
accumulators and of core). These tests require `python -m nexo_os seed` to have run.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from nexo_os.data.factory import get_repository
from nexo_os.data.ground_truth import ground_truth_path, load_ground_truth
from nexo_os.data.models import CuotaEstado, PolizaEstado

pytestmark = pytest.mark.skipif(
    not ground_truth_path().exists(), reason="run `python -m nexo_os seed` first"
)


@pytest.fixture(scope="module")
def repo():
    return get_repository()


@pytest.fixture(scope="module")
def gt():
    return load_ground_truth()


def test_counts_match(repo, gt) -> None:
    assert len(repo.get_clientes()) == gt["counts"]["clientes"]
    assert len(repo.get_polizas()) == gt["counts"]["polizas"]
    assert len(repo.get_cuotas()) == gt["counts"]["cuotas"]
    assert len(repo.get_comisiones()) == gt["counts"]["comisiones"]


def test_overdue_universe_is_exactly_planted(repo, gt) -> None:
    """No baseline installment is overdue: the vencida set equals the planted set."""
    vencidas = repo.get_cuotas(estado=CuotaEstado.vencida)
    assert len(vencidas) == gt["morosidad"]["total_count"]
    assert {c.cuota_id for c in vencidas} == set(gt["morosidad"]["cuota_ids"])
    total = sum((c.monto_ars for c in vencidas), Decimal("0"))
    assert total == Decimal(gt["morosidad"]["total_vencido_ars"])


def test_morosidad_buckets_sum_to_total(gt) -> None:
    m = gt["morosidad"]
    assert sum(b["count"] for b in m["buckets"].values()) == m["total_count"]


def test_no_baseline_near_term_expiry(repo, gt) -> None:
    """Only planted policies expire within 90 days of the snapshot."""
    snap = repo.snapshot_fecha
    vigentes = repo.get_polizas(estado=PolizaEstado.vigente)
    within_90 = [p for p in vigentes if 0 <= (p.fecha_fin_vigencia - snap).days <= 90]
    assert len(within_90) == gt["renewals"]["expira_total_90d_count"]


def test_cartera_reconciles_with_current_period_commissions(repo, gt) -> None:
    """cartera commission total ties to the current-period comisiones rows."""
    snap = repo.snapshot_fecha
    current_period = f"{snap.year:04d}-{snap.month:02d}"
    current = repo.get_comisiones(periodo=current_period)
    esperada_sum = sum((c.comision_esperada_ars for c in current), Decimal("0"))
    assert esperada_sum == Decimal(gt["cartera"]["comision_esperada_ars"])

    vigentes = repo.get_polizas(estado=PolizaEstado.vigente)
    prima_sum = sum((p.prima_ars for p in vigentes), Decimal("0"))
    assert prima_sum == Decimal(gt["cartera"]["prima_total_ars"])
    assert len(vigentes) == gt["cartera"]["polizas_vigentes"]


def test_caucion_loss_ratio_matches(repo, gt) -> None:
    from nexo_os.data.models import Ramo, SiniestroEstado

    caucion = repo.get_polizas(ramo=Ramo.caucion)
    premium = sum((p.prima_ars for p in caucion), Decimal("0"))
    assert premium == Decimal(gt["profitability"]["caucion_premium_ars"])

    caucion_ids = {p.poliza_id for p in caucion}
    paid = sum(
        (s.monto_pagado_ars or Decimal("0"))
        for s in repo.get_siniestros(estado=SiniestroEstado.pagado)
        if s.poliza_id in caucion_ids
    )
    assert paid == Decimal(gt["profitability"]["caucion_claims_paid_ars"])


def test_commission_discrepancies_present(repo, gt) -> None:
    from nexo_os.data.models import ComisionEstado

    disc = repo.get_comisiones(estado=ComisionEstado.con_diferencia)
    assert {c.comision_id for c in disc} == set(gt["comisiones"]["discrepancia_ids"])
    total = sum((c.diferencia_ars for c in disc), Decimal("0"))
    assert total == Decimal(gt["comisiones"]["total_diferencia_ars"])


def test_inactive_clients_have_no_inforce_policy(repo, gt) -> None:
    from nexo_os.data.models import ClienteEstado

    inactivos = repo.get_clientes(estado=ClienteEstado.inactivo)
    assert {c.cliente_id for c in inactivos} == set(gt["inactivos_sin_poliza_ids"])
    vigentes = repo.get_polizas(estado=PolizaEstado.vigente)
    inforce_clients = {p.cliente_id for p in vigentes}
    assert all(c.cliente_id not in inforce_clients for c in inactivos)
