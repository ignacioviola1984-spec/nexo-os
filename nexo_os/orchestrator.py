"""Orchestrator: runs one full cycle.

  load repository for the snapshot
  -> each agent computes (deterministic)
  -> deterministic cross-checks / reconciliations
  -> each agent proposes (deterministic confidence/priority)
  -> narrate (model) with the grounding check
  -> persist acciones, agent_runs, audit_log
  -> return the populated NexoContext

Fails closed: on an unhandled error the run is marked `error` and surfaced; partial
numbers are never emitted as if complete.
"""

from __future__ import annotations

import json
import uuid

from nexo_os import reliability
from nexo_os.agents.base import Agent
from nexo_os.agents.specialists import all_agents
from nexo_os.audit import AuditWriter
from nexo_os.clock import now
from nexo_os.config import Settings, get_settings
from nexo_os.data.models import AgentRun, RunEstado
from nexo_os.data.repository import NexoRepository
from nexo_os.enterprise.observability import METRICS
from nexo_os.logging_setup import bind_run_id, clear_run_context, get_logger
from nexo_os.narrate import narrate
from nexo_os.state import NexoContext

log = get_logger("orchestrator")

# priority order for capping model narration (highest first)
_PRIO_RANK = {"alta": 0, "media": 1, "baja": 2}


def _narrate_all(acciones, settings: Settings):
    """Fill mensaje_es for each action. Model narration is capped by cost; the rest
    get the deterministic grounded facts. Order: priority, then amount at stake."""
    cap = settings.narrate_model_cap
    key = bool(settings.anthropic_api_key)
    ordered = sorted(
        range(len(acciones)),
        key=lambda i: (
            _PRIO_RANK.get(acciones[i].prioridad.value, 3),
            -(float(acciones[i].monto_en_juego_ars) if acciones[i].monto_en_juego_ars else 0.0),
        ),
    )
    use_model_idx = set(ordered[:cap]) if key else set()
    out = []
    for i, a in enumerate(acciones):
        msg = narrate(a, settings=settings, allow_model=(i in use_model_idx))
        out.append(a.model_copy(update={"mensaje_es": msg}))
    return out


def run_cycle(
    repo: NexoRepository | None = None,
    settings: Settings | None = None,
    agents: list[Agent] | None = None,
) -> NexoContext:
    settings = settings or get_settings()
    if repo is None:
        from nexo_os.data.factory import get_repository

        repo = get_repository()
    agents = agents or all_agents()

    run_id = uuid.uuid4().hex
    bind_run_id(run_id)
    audit = AuditWriter(repo)
    ctx = NexoContext(repo=repo, run_id=run_id, snapshot_fecha=repo.snapshot_fecha)
    iniciado = now()

    repo.insert_agent_run(
        AgentRun(
            run_id=run_id,
            iniciado_en=iniciado,
            finalizado_en=None,
            estado=RunEstado.ok,
            resumen_json="{}",
            data_source=repo.data_source,
            data_snapshot_fecha=repo.snapshot_fecha,
        )
    )
    audit.record(
        actor="system",
        accion="run_started",
        entidad_tipo="run",
        entidad_id=run_id,
        detalle={"data_source": repo.data_source, "snapshot": repo.snapshot_fecha.isoformat()},
    )

    try:
        log.info("run.compute_start", agents=len(agents))
        for agent in agents:
            ctx.put_result(agent.id, agent.compute(ctx))

        # reliability layer: deterministic reconciliations
        for severidad, mensaje in reliability.reconcile(ctx):
            ctx.add_warning(severidad, mensaje)
            audit.record(
                actor="system",
                accion="reconciliation_warning",
                entidad_tipo="run",
                entidad_id=run_id,
                detalle={"severidad": severidad, "mensaje": mensaje},
            )

        # propose + narrate
        for agent in agents:
            result = ctx.get_result(agent.id)
            proposed = agent.propose(ctx, result)
            proposed = _narrate_all(proposed, settings)
            ctx.add_acciones(proposed)

        if ctx.acciones:
            repo.insert_acciones(ctx.acciones)

        estado = RunEstado.con_warnings if ctx.warnings else RunEstado.ok
    except Exception as exc:
        finalizado = now()
        if settings.metrics_enabled:
            METRICS.inc("nexo_agent_runs_total", estado="error")
        repo.update_agent_run(run_id, finalizado, RunEstado.error, json.dumps({"error": str(exc)}))
        audit.record(
            actor="system",
            accion="run_error",
            entidad_tipo="run",
            entidad_id=run_id,
            detalle={"error": str(exc)},
        )
        log.error("run.error", error=str(exc))
        clear_run_context()
        raise

    finalizado = now()
    resumen = ctx.resumen()
    if settings.metrics_enabled:
        METRICS.inc("nexo_agent_runs_total", estado=estado.value)
        METRICS.inc("nexo_acciones_total", value=float(len(ctx.acciones)))
        METRICS.inc("nexo_reconciliation_breaks_total", value=float(len(ctx.warnings)))
        freshness_h = (finalizado.date() - repo.snapshot_fecha).days * 24.0
        METRICS.set_gauge("nexo_data_freshness_hours", freshness_h)
    repo.update_agent_run(run_id, finalizado, estado, json.dumps(resumen, ensure_ascii=False))
    audit.record(
        actor="system",
        accion="run_finished",
        entidad_tipo="run",
        entidad_id=run_id,
        detalle={"estado": estado.value, "acciones": resumen["acciones_total"]},
    )
    log.info("run.finished", estado=estado.value, acciones=resumen["acciones_total"])
    clear_run_context()
    return ctx
