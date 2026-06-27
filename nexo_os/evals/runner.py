"""Eval / guardrail harness. Runs as a regression gate: exits non-zero on any
failure (`python -m nexo_os eval`). Treat a red eval exactly like a failed test.

Suites:
  1. Numbers regression  — core metrics match GROUND_TRUTH exactly
  2. Agent detection     — each agent surfaces its planted set
  3. Grounding guardrail — every number in prose is in the rationale; invented fails
  4. PII minimization    — narrate inputs carry no full documento/email/telefono/birth
  5. Refusal / sin datos — missing inputs yield explicit None, never a fabricated value
  6. Reconciliation      — cross-agent reconciliations hold within tolerance
  7. Audit integrity     — the hash chain verifies after a run with an approval
"""

from __future__ import annotations

import json
import re
import tempfile
from decimal import Decimal
from pathlib import Path

from nexo_os.agents.specialists import all_agents
from nexo_os.audit import AuditWriter, verify_chain
from nexo_os.config import Settings, get_settings
from nexo_os.core import cartera, renewals
from nexo_os.data.factory import get_repository
from nexo_os.data.ground_truth import ground_truth_path, load_ground_truth
from nexo_os.data.models import AccionEstado
from nexo_os.grounding import is_grounded
from nexo_os.narrate import deterministic_facts
from nexo_os.reliability import reconcile
from nexo_os.review import resolve_accion
from nexo_os.state import NexoContext

_PII_PATTERNS = [
    re.compile(r"@example\.com"),  # synthetic emails
    re.compile(r"\+54-\d"),  # phones
    re.compile(r"\b20-99\d{6}-\d\b"),  # synthetic documents
]


def _ctx(repo) -> NexoContext:
    return NexoContext(repo=repo, run_id="eval", snapshot_fecha=repo.snapshot_fecha)


def _all_proposed(repo) -> list:
    ctx = _ctx(repo)
    acciones = []
    for agent in all_agents():
        result = agent.compute(ctx)
        ctx.put_result(agent.id, result)
        acciones.extend(agent.propose(ctx, result))
    return acciones


# --- suites --------------------------------------------------------------------


def suite_numbers(repo, gt) -> list[str]:
    fails: list[str] = []
    ctx = _ctx(repo)
    car = cartera.compute(ctx.polizas, ctx.thresholds)
    if car.prima_total_ars != Decimal(gt["cartera"]["prima_total_ars"]):
        fails.append("cartera prima_total mismatch")
    if car.comision_esperada_ars != Decimal(gt["cartera"]["comision_esperada_ars"]):
        fails.append("cartera comision_esperada mismatch")

    from nexo_os.core import comisiones, morosidad, profitability

    mor = morosidad.compute(ctx.cuotas, ctx.snapshot_fecha, ctx.thresholds)
    if mor.total_vencido_ars != Decimal(gt["morosidad"]["total_vencido_ars"]):
        fails.append("morosidad total mismatch")

    com = comisiones.compute(ctx.comisiones, ctx.snapshot_fecha, ctx.thresholds)
    if com.diferencia_total_ars != Decimal(gt["comisiones"]["total_diferencia_ars"]):
        fails.append("comisiones diferencia mismatch")

    prof = profitability.compute(ctx.polizas, ctx.siniestros, ctx.thresholds)
    if prof.por_ramo["caucion"]["loss_ratio"] != Decimal(gt["profitability"]["caucion_loss_ratio"]):
        fails.append("profitability caucion loss ratio mismatch")
    return fails


def suite_detection(repo, gt) -> list[str]:
    fails: list[str] = []
    ctx = _ctx(repo)
    by_id = {a.id: a for a in all_agents()}

    def proposed(agent_id):
        ag = by_id[agent_id]
        return ag.propose(ctx, ag.compute(ctx))

    cob = {json.loads(a.rationale_json)["numeros"]["cuota_id"] for a in proposed("cobranza")}
    if cob != set(gt["morosidad"]["cuota_ids"]):
        fails.append("cobranza did not surface exactly the overdue set")

    ren = {a.entidad_id for a in proposed("renewals")}
    expected_ren = set(
        gt["renewals"]["expira_30_ids"]
        + gt["renewals"]["expira_60_ids"]
        + gt["renewals"]["expira_90_ids"]
    )
    if ren != expected_ren:
        fails.append("renewals did not surface exactly the expiring set")

    ret = {a.entidad_id for a in proposed("retention")}
    if ret != set(gt["retention"]["at_risk_client_ids"]):
        fails.append("retention did not surface exactly the at-risk clients")

    lc = proposed("leads_control")
    sla = {a.entidad_id for a in lc if a.tipo_accion == "contactar_lead_sla"}
    npq = {a.entidad_id for a in lc if a.tipo_accion == "presentar_cotizacion"}
    if sla != set(gt["leads_control"]["sla_breach_ids"]):
        fails.append("leads_control did not surface exactly the SLA breaches")
    if npq != set(gt["leads_control"]["quotes_no_presentadas_ids"]):
        fails.append("leads_control did not surface exactly the unpresented quotes")

    prof = {a.entidad_id for a in proposed("profitability")}
    if prof != set(gt["profitability"]["unprofitable_ramos"]):
        fails.append("profitability did not surface exactly the unprofitable ramos")
    return fails


def suite_grounding(repo, gt) -> list[str]:
    fails: list[str] = []
    acciones = _all_proposed(repo)
    for a in acciones:
        payload = json.loads(a.rationale_json)
        facts = deterministic_facts(a)
        if not is_grounded(facts, payload):
            fails.append(f"deterministic facts not grounded for {a.accion_id} ({a.tipo_accion})")
            break
    # the wall must reject an invented figure
    if acciones:
        payload = json.loads(acciones[0].rationale_json)
        if is_grounded(deterministic_facts(acciones[0]) + " ARS 999.999.999", payload):
            fails.append("grounding wall accepted an invented number")
    return fails


def suite_pii(repo, gt) -> list[str]:
    """The only thing narrate receives is the action (rationale + facts). Assert no
    full documento/email/telefono leaks into either."""
    fails: list[str] = []
    for a in _all_proposed(repo):
        blob = a.rationale_json + " " + deterministic_facts(a)
        for pat in _PII_PATTERNS:
            if pat.search(blob):
                fails.append(f"PII leaked into narrate input for {a.accion_id}: {pat.pattern}")
                return fails
    return fails


def suite_refusal(repo, gt) -> list[str]:
    fails: list[str] = []
    ctx = _ctx(repo)
    car = cartera.compute(ctx.polizas, ctx.thresholds)
    if car.crecimiento_mom is not None or car.crecimiento_yoy is not None:
        fails.append("cartera growth should be None (sin datos) without history")
    # renewals renewal_rate is None when there is no renovada/vencida basis
    ren = renewals.compute(
        ctx.polizas, ctx.siniestros, ctx.cuotas, ctx.snapshot_fecha, ctx.thresholds
    )
    if ren.renewal_rate is not None and not (Decimal("0") <= ren.renewal_rate <= Decimal("1")):
        fails.append("renewals rate fabricated out of range")
    from nexo_os.i18n import SIN_DATOS, fmt_ars

    if fmt_ars(None) != SIN_DATOS:
        fails.append("None amount must render as 'sin datos', never a zero")
    return fails


def suite_reconciliation(repo, gt) -> list[str]:
    ctx = _ctx(repo)
    for agent in all_agents():
        ctx.put_result(agent.id, agent.compute(ctx))
    warnings = reconcile(ctx)
    return [f"reconciliation break: {m}" for _, m in warnings]


def suite_audit(repo, gt) -> list[str]:
    """Run a cycle into a fresh runtime store, approve one action, verify the chain."""
    from nexo_os.data.synthetic import SyntheticRepository
    from nexo_os.orchestrator import run_cycle

    s = get_settings()
    tmp = Path(tempfile.mkdtemp(prefix="nexo_eval_"))
    eval_repo = SyntheticRepository(
        synthetic_db_path=s.synthetic_db_path,
        runtime_db_path=tmp / "rt.duckdb",
        snapshot_fecha=s.synthetic_snapshot_fecha,
    )
    ctx = run_cycle(repo=eval_repo, settings=Settings(ANTHROPIC_API_KEY=None))
    fails: list[str] = []
    pendientes = eval_repo.get_acciones(estado=AccionEstado.propuesta)
    if not pendientes:
        return ["no actions proposed to approve"]
    audit = AuditWriter(eval_repo)
    resolve_accion(eval_repo, audit, pendientes[0].accion_id, AccionEstado.aprobada, "eval")
    chk = verify_chain(eval_repo.get_audit_events())
    if not chk.ok:
        fails.append(f"audit chain broken at #{chk.broken_at}")
    if eval_repo.get_acciones(estado=AccionEstado.aprobada)[0].accion_id != pendientes[0].accion_id:
        fails.append("approval not recorded")
    _ = ctx
    return fails


SUITES = [
    ("1. Números (regresión)", suite_numbers),
    ("2. Detección de agentes", suite_detection),
    ("3. Grounding (cifras)", suite_grounding),
    ("4. PII minimización", suite_pii),
    ("5. Refusal / sin datos", suite_refusal),
    ("6. Reconciliación", suite_reconciliation),
    ("7. Integridad de auditoría", suite_audit),
]


def main() -> int:
    if not ground_truth_path().exists():
        print("eval: ground truth not found. Run `python -m nexo_os seed` first.")
        return 2
    repo = get_repository()
    gt = load_ground_truth()
    total_fail = 0
    print("=== Nexo eval harness ===")
    for name, fn in SUITES:
        try:
            fails = fn(repo, gt)
        except Exception as exc:  # a crashing suite is a failure
            fails = [f"excepción: {exc}"]
        status = "OK" if not fails else f"FALLA ({len(fails)})"
        print(f"  {name:32} {status}")
        for f in fails:
            print(f"      - {f}")
        total_fail += len(fails)
    print("=" * 40)
    if total_fail:
        print(f"EVAL ROJO: {total_fail} fallas.")
        return 1
    print("EVAL VERDE: todas las suites pasaron.")
    return 0
