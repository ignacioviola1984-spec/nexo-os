# Changelog

All notable changes to this project are documented here. Versioning is
[SemVer](https://semver.org/). Public repo = the sanitized architecture + a
synthetic exercise of it; the live deployment runs privately over the brokerage's
data (see README → "Same code path").

## [Unreleased]

### Added
- **GCS data source** (`NEXO_DATA_SOURCE=gcs`): reads domain extracts (Parquet)
  from a Google Cloud Storage bucket into a local store and serves them through the
  same `NexoRepository` interface. Fails closed without bucket/credentials/library,
  same standard as BigQuery. Optional dep: `pip install -e ".[gcs]"`.
- **Multi-tenancy by per-tenant data isolation** (`NEXO_TENANT_ID`): each tenant's
  data lives in its own store / BigQuery dataset / GCS prefix; `default` keeps the
  original single-tenant paths. Agents, core, and schema are untouched — tenancy
  lives at the `get_repository(tenant_id=...)` seam.

## [2.0.0] - 2026-06-30

Production operating model for a single insurance brokerage: ten deterministic
agents, human-in-the-loop approval inbox, hash-chained audit, pluggable data
backends.

### Added
- Ten specialist agents (cartera, morosidad, cobranza, comisiones, renovaciones,
  retention, conversión, pipeline, leads-control, profitability) over a
  deterministic core; the language model interprets/prioritizes/writes Spanish
  prose and never produces a figure.
- Pluggable data layer behind one `NexoRepository` interface, selected by
  `NEXO_DATA_SOURCE`: `synthetic` (local DuckDB) and `bigquery` (production).
- Self-bootstrapping public demo (`streamlit_app.py`, `demo_mode`) + CV/portfolio
  landing; zero secrets, 100% synthetic.
- HITL approval inbox + append-only, hash-chained audit log.
- Eval/guardrail harness (`python -m nexo_os eval`) — determinism, grounding,
  PII minimization, reconciliation, audit integrity.
- CI pipeline (GitHub Actions): lint → seed → tests → eval gate.
- `scripts/run_datasets.py` + `docs/EVIDENCE.md`: pipeline run across multiple
  synthetic datasets.

### Notes
- Outbound execution is human-driven by design (the only execution adapter is a
  no-op that records "would execute" to the audit log). This is a deliberate
  control, not end-to-end automation.
