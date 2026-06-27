"""Phase 5: each agent surfaces its planted ground-truth set as proposed actions
(the detection eval, exercised through the agent contract). Requires `seed`."""

from __future__ import annotations

import json

import pytest

from nexo_os.agents.specialists import (
    CobranzaAgent,
    ComisionesAgent,
    LeadsControlAgent,
    PipelineAgent,
    ProfitabilityAgent,
    RenewalsAgent,
    RetentionAgent,
)
from nexo_os.data.factory import get_repository
from nexo_os.data.ground_truth import ground_truth_path, load_ground_truth
from nexo_os.state import NexoContext

pytestmark = pytest.mark.skipif(
    not ground_truth_path().exists(), reason="run `python -m nexo_os seed` first"
)


@pytest.fixture(scope="module")
def ctx():
    repo = get_repository()
    return NexoContext(repo=repo, run_id="TEST", snapshot_fecha=repo.snapshot_fecha)


@pytest.fixture(scope="module")
def gt():
    return load_ground_truth()


def _nums(acciones):
    return [json.loads(a.rationale_json)["numeros"] for a in acciones]


def _run(agent, ctx):
    result = agent.compute(ctx)
    return agent.propose(ctx, result)


def test_cobranza_surfaces_every_overdue(ctx, gt) -> None:
    acciones = _run(CobranzaAgent(), ctx)
    cuota_ids = {n["cuota_id"] for n in _nums(acciones)}
    assert cuota_ids == set(gt["morosidad"]["cuota_ids"])


def test_renewals_surfaces_expiring_and_at_risk(ctx, gt) -> None:
    acciones = _run(RenewalsAgent(), ctx)
    poliza_ids = {a.entidad_id for a in acciones}
    expected = set(
        gt["renewals"]["expira_30_ids"]
        + gt["renewals"]["expira_60_ids"]
        + gt["renewals"]["expira_90_ids"]
    )
    assert poliza_ids == expected
    at_risk = {n["poliza_id"] for n in _nums(acciones) if n["en_riesgo"]}
    assert at_risk == set(gt["renewals"]["at_risk_ids"])


def test_comisiones_surfaces_discrepancies_and_receivable(ctx, gt) -> None:
    acciones = _run(ComisionesAgent(), ctx)
    ids = {a.entidad_id for a in acciones}
    expected = set(gt["comisiones"]["discrepancia_ids"]) | set(
        gt["comisiones"]["receivable_aged_ids"]
    )
    assert ids == expected


def test_leads_control_surfaces_sla_and_unpresented(ctx, gt) -> None:
    acciones = _run(LeadsControlAgent(), ctx)
    sla = {a.entidad_id for a in acciones if a.tipo_accion == "contactar_lead_sla"}
    np = {a.entidad_id for a in acciones if a.tipo_accion == "presentar_cotizacion"}
    assert sla == set(gt["leads_control"]["sla_breach_ids"])
    assert np == set(gt["leads_control"]["quotes_no_presentadas_ids"])


def test_retention_surfaces_at_risk_clients(ctx, gt) -> None:
    acciones = _run(RetentionAgent(), ctx)
    ids = {a.entidad_id for a in acciones}
    assert ids == set(gt["retention"]["at_risk_client_ids"])


def test_profitability_surfaces_unprofitable_ramo(ctx, gt) -> None:
    acciones = _run(ProfitabilityAgent(), ctx)
    ramos = {a.entidad_id for a in acciones}
    assert ramos == set(gt["profitability"]["unprofitable_ramos"])


def test_pipeline_surfaces_aging(ctx, gt) -> None:
    acciones = _run(PipelineAgent(), ctx)
    ids = {a.entidad_id for a in acciones}
    assert ids == set(gt["pipeline"]["aging_ids"])


def test_proposed_actions_have_deterministic_priority_and_confidence(ctx) -> None:
    acciones = _run(CobranzaAgent(), ctx)
    assert acciones, "expected overdue actions"
    for a in acciones:
        assert 0.0 <= a.confianza <= 1.0
        assert a.prioridad.value in {"alta", "media", "baja"}
        assert a.mensaje_es == ""  # not yet narrated
