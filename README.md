# Nexo Operating Model

Production analytics-and-action system for a single Argentine insurance brokerage.
Ten specialist agents read the broker's data, compute the state of the business
**deterministically**, surface what needs attention, and **propose actions that a
human approves** before anything is considered done.

## Nexo OS Operating Model

![Nexo OS Operating Model](docs/nexo-os-operating-model.png)

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

Deployed. Data source in this repo is synthetic by default for PII and client-confidentiality reasons.

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
- [`docs/BIGQUERY_CUTOVER.md`](docs/BIGQUERY_CUTOVER.md) — BigQuery cutover runbook.

## Language

Code, identifiers, comments, commits, docs: **English**. UI strings and all
model-generated prose for staff: **Spanish (rioplatense)**. Money in ARS.
