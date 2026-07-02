# Nexo Operating Model

Production analytics-and-action system for a single Argentine insurance brokerage.
Ten specialist agents read the broker's data, compute the state of the business
**deterministically**, surface what needs attention, and **propose actions that a
human approves** before anything is considered done.

![Nexo OS Operating Model](Diagrama%20del%20modelo%20operativo%20Nexo%20OS.png)

## Three non-negotiables

1. **Every number is computed in code, deterministically, and is traceable to its
   inputs.** The language model never produces, estimates, rounds, or fills in a
   figure. It routes, prioritizes, and writes Spanish prose. If a number cannot be
   computed, the system says so — it never invents one.
2. **Human-in-the-loop at every action.** Agents propose; a person approves.
   Approvals are recorded immutably. Outbound execution is human-driven by design.
3. **It fails closed.** Missing data, a failed check, or low confidence → flag and
   stop, never guess and proceed.

## Status

Deployed and in production use for a single brokerage. Data source in this repo is
synthetic by default for PII and client-confidentiality reasons. This is the
sanitized public version of the deployed architecture.

## Same code path: the demo runs the production logic

The public synthetic demo is **not** a separate showcase build. The ten agents, the
deterministic core, the orchestrator, the cross-agent reconciliations, the HITL
approval inbox, and the hash-chained audit log are **identical** in the demo and in
the live deployment. Only the data backend changes, at a single seam:

`get_repository()` ([`nexo_os/data/factory.py`](nexo_os/data/factory.py)) returns the
backend for `NEXO_DATA_SOURCE` — agents and core depend only on the `NexoRepository`
interface; nothing else knows which backend is live:

- **`synthetic`** — local DuckDB over generated data (the default; the public demo).
- **`bigquery`** — the brokerage's live data warehouse (production).
- **`gcs`** — cloud object storage: domain extracts as Parquet in a Google Cloud
  Storage bucket, loaded into a local store and served identically. Fails closed
  without bucket/credentials.
- **`turso`** — hosted libSQL (SQLite-compatible). Money is stored exactly as TEXT
  (never float), coerced back to `Decimal` on read. Fails closed without a database URL.

Beyond a full data source, Turso can also serve **just the system tables**: set
`NEXO_SYSTEM_STORE=turso` to keep domain reads on synthetic/BigQuery/GCS while
persisting `acciones`, `agent_runs`, and the hash-chained `audit_log` in Turso — so
approvals and the audit trail survive a restart (see [`docs/TURSO.md`](docs/TURSO.md)).

So the demo here exercises the same code that runs in production. The real store,
uploads, users, and audit log stay private (gitignored) for PII and
client-confidentiality reasons — what's public is the architecture and a synthetic
exercise of it, not the client's data.

## Multi-tenancy (per-tenant data isolation)

The system is multi-tenant by **hard data isolation**: the active tenant
(`NEXO_TENANT_ID`) selects an isolated store / BigQuery dataset / GCS prefix, so a
brokerage's data never shares a table with another's. The `default` tenant keeps the
original paths (single-tenant behavior, unchanged). This is deployment-/process-per
-tenant isolation — preferred for regulated, PII-bearing data over a shared
`tenant_id` column. Agents, core, and the schema are untouched by tenancy; it lives
at the `get_repository(tenant_id=...)` seam.

## Scope & positioning

A focused, **single-brokerage** operating model — deliberately not a
multi-insurer quoting engine or a public-signup SaaS. What it is, on a maturity
ladder:

| Level | Capability | Status |
|---|---|---|
| L1 | Observe — deterministic metrics over the book | done |
| L2 | **Propose + human-in-the-loop inbox** (approve / edit / reject, audited) | **current** |
| L3 | Assisted execution — one-click outbound, still human-approved | seam ready, disabled |
| L4 | Automated execution — policy-bounded, no human per action | out of scope |

**Outbound execution is human-driven by design.** Approved actions are recorded;
the execution adapter ([`nexo_os/security/execution.py`](nexo_os/security/execution.py)
— `NoopExecutionAdapter`) records a "would execute" event and performs **no**
external side effect. The seam is pluggable but disabled. So this is a deployed
**decision / operating** model at **L2** — *not* end-to-end automation. That
boundary is a deliberate control for a system that touches money and PII.

### Public vs private

- **Public (this repo):** the architecture + a synthetic exercise of it — code,
  tests, the eval gate, CI, and a synthetic dataset. Safe to read; no client data.
- **Private (the live deployment):** the brokerage's real store, uploads, users,
  and audit log — never committed (gitignored) for PII / confidentiality. **Same
  code path** (above); only the data backend differs.
- **Evidence:** synthetic multi-dataset pipeline runs are in
  [`docs/EVIDENCE.md`](docs/EVIDENCE.md); anonymized production aggregates (counts
  only, no identities) go in [`docs/PRODUCTION_EVIDENCE.md`](docs/PRODUCTION_EVIDENCE.md).

## Quick start (synthetic, two commands after setup)

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate on POSIX
pip install -e ".[dev]"

cp .env.example .env              # then set ANTHROPIC_API_KEY and NEXO_ADMIN_PASSWORD

python -m nexo_os seed            # generate synthetic data
python -m nexo_os bootstrap-admin # provision the initial admin seat from .env
python -m nexo_os run             # launch the Spanish dashboard
```

`make` targets exist as thin wrappers (`make seed`, `make run`, …) but `make` is
optional — every target maps 1:1 to `python -m nexo_os <command>`.

## Commands

| Command | What it does |
|---|---|
| `seed` | Generate synthetic data into the local DuckDB store |
| `bootstrap-admin` | Provision the initial admin seat from `.env` |
| `run` | Launch the Streamlit dashboard |
| `orchestrate` | Run one full orchestrator cycle headless |
| `test` | Run pytest |
| `eval` | Run the eval/guardrail harness (exits non-zero on failure) |
| `lint` | ruff + black checks |
| `bq-validate` | Validate a live BigQuery dataset vs the canonical DDL |
| `turso-seed` | Load the synthetic dataset into the configured Turso database |
| `healthcheck` | Liveness/readiness probe (JSON); non-zero when not ready |
| `controls-check` | SOC2-style control self-assessment (non-zero on any FAIL) |
| `security-review` | Automated security review (non-zero on HIGH/CRITICAL) |
| `data-contract-validate` | Validate the active domain source vs the data contracts |
| `rotate-secret cookie` | Print a cookie-key rotation plan |
| `iam-validate` | Validate the cloud IAM group->role bindings |
| `incident-report` | Snapshot state + record an incident to the audit log |
| `release-manifest` / `rollback-check` | Release identity + schema-guarded rollback |

## Enterprise / production hardening

RBAC, SSO/OIDC, cloud IAM, observability, data contracts, secret rotation, controls,
security review, release/rollback, and incident response - added as real, tested code on
top of the deterministic HITL core, without changing how any figure is computed. Seams
(SSO, cloud IAM, cloud secret managers) fail closed until configured, and the control
harness and security review *check* the posture rather than assert a certification. See
[`docs/ENTERPRISE.md`](docs/ENTERPRISE.md) for the twelve concerns and their status.

## Documentation

- [`OPERATING-MODEL.md`](OPERATING-MODEL.md) — how it works; the determinism / HITL boundary.
- [`nexo_os/data/schema/DATA_MODEL.md`](nexo_os/data/schema/DATA_MODEL.md) — canonical schema, grains, PII flags.
- [`docs/TURSO.md`](docs/TURSO.md) — the Turso/libSQL backend (full + hybrid system store).
- [`docs/ENTERPRISE.md`](docs/ENTERPRISE.md) — the enterprise hardening layer (RBAC, SSO, IAM, observability, controls, rollback, incident response).
- [`docs/SOC2_CONTROLS.md`](docs/SOC2_CONTROLS.md) · [`docs/SECURITY_REVIEW.md`](docs/SECURITY_REVIEW.md) · [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md) · [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) · [`docs/INCIDENT_RESPONSE.md`](docs/INCIDENT_RESPONSE.md)
- [`SECURITY.md`](SECURITY.md) — auth, PII handling, the disabled execution seam, audit chain.

## Language

Code, identifiers, comments, commits, docs: **English**. UI strings and all
model-generated prose for staff: **Spanish (rioplatense)**. Money in ARS.
