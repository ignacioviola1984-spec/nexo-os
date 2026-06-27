# Nexo operating model

How the system works, and where the hard boundaries are.

## The three non-negotiables

1. **Every number is computed in code, deterministically, traceable to its inputs.**
   The language model never produces, estimates, rounds, or fills in a figure.
2. **Human-in-the-loop at every action.** Agents propose; a person approves.
   Approvals are recorded immutably.
3. **It fails closed.** Missing data / failed check / low confidence → flag and stop.

Everything below serves these three.

## The determinism / HITL boundary

```
        DETERMINISTIC (code)                         HUMAN                MODEL
  ┌──────────────────────────────┐          ┌──────────────────┐   ┌─────────────┐
  repository → core metrics → Hallazgos → propose (confidence,    inbox: approve/   narrate:
  (typed, snapshot)  (Decimal)   (numbers)   priority) → Accion    reject/edit →     Spanish prose
                                              (rationale_json)      audit_log         over the numbers
                                                                                      (grounding-checked)
```

- **Numbers** are born in `nexo_os/core/*` as `Decimal`, over typed objects from the
  repository, at one snapshot date. They never leave that layer except as data.
- **Confidence and priority** are deterministic functions (`agents/base.py`):
  confidence = 0.5·completeness + 0.5·signal; priority routes by amount at stake, or by
  urgency when there is no natural amount (never defaulted).
- **The model** (`narrate.py`) only writes prose, and only from the rationale. The
  grounding guardrail (`grounding.py`) verifies every number in the prose traces to the
  rationale; if not (or no API key), the system uses deterministic, grounded text.
- **The human** resolves each action in the inbox. Nothing is "done" until then.
  Resolutions are hash-chained into `audit_log`.

## Components

| Layer | Module | Role |
|---|---|---|
| Config | `config.py` | settings + all tunable thresholds (no magic numbers in agents) |
| Data access | `data/repository.py`, `data/synthetic.py`, `data/bigquery.py`, `data/factory.py` | one typed interface; synthetic now, BigQuery deferred |
| Schema | `data/schema_def.py` | single source → DDL (both dialects) + PII registry |
| Core | `core/*` | deterministic metric library |
| State | `state.py` | shared, memoized snapshot + results |
| Agents | `agents/specialists.py` | 10 specialists: compute → propose → narrate |
| Governance | `review.py`, `audit.py`, `reliability.py`, `security/*` | maker-checker, hash chain, cross-checks, PII, execution seam |
| Orchestrator | `orchestrator.py` | the full cycle + persistence |
| Dashboard | `dashboard/app.py` | Spanish UI; the inbox is the spine |
| Evals | `evals/runner.py` | regression gate (exits non-zero) |

## The cycle (`run_cycle`)

1. Load the repository for the snapshot (one consistent "as of" date).
2. Each agent `compute`s its figures from core (no model).
3. Deterministic reconciliations run (`reliability.reconcile`); breaks → warnings,
   the run is marked `con_warnings` (never silently averaged).
4. Each agent `propose`s actions (deterministic confidence/priority).
5. `narrate` fills the Spanish message (model for the top actions, grounded facts for
   the rest); grounding is checked.
6. Persist `acciones`, `agent_runs`, `audit_log`. Return the populated `NexoContext`.

## The ten agents

cartera, cobranza, morosidad, renovaciones (renewals), retención (retention),
conversión, pipeline, control de leads/cotizaciones (leads_control), rentabilidad
(profitability), seguimiento de comisiones (comisiones).

Cross-agent reconciliations that must hold: cobranza ↔ morosidad (overdue total),
cartera ↔ comisiones (expected commission, current period), profitability ↔ cartera
(net commission).

## Reproducibility & ground truth

The synthetic generator plants detectable situations and records their EXACT ground
truth (`data/synthetic/GROUND_TRUTH.md` + `ground_truth.json`) via an accumulator
independent of `core`. The golden tests and eval suite assert that core and the agents
reproduce that ground truth exactly — so a bug on either side is caught.

## What is deferred / out of scope (this build)

- Live BigQuery connection (scaffolded, fails closed; see `BIGQUERY_CUTOVER.md`).
- Any outbound execution (the execution seam is disabled).
- Multi-tenant features, public sign-up, billing.
