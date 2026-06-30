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

## Documentation

- [`OPERATING-MODEL.md`](OPERATING-MODEL.md) — how it works; the determinism / HITL boundary.
- [`nexo_os/data/schema/DATA_MODEL.md`](nexo_os/data/schema/DATA_MODEL.md) — canonical schema, grains, PII flags.
- [`SECURITY.md`](SECURITY.md) — auth, PII handling, the disabled execution seam, audit chain.

## Language

Code, identifiers, comments, commits, docs: **English**. UI strings and all
model-generated prose for staff: **Spanish (rioplatense)**. Money in ARS.
