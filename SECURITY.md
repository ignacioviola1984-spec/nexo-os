# Security & data handling

Nexo is single-tenant but touches money (premiums, commissions, collections) and
client PII. This document states what data exists, where it lives, what is sent to
the model, and the controls around it.

## Data inventory

| Data | Where it lives | Sensitivity |
|---|---|---|
| Domain data (clients, policies, installments, commissions, leads, quotes, claims) | **Synthetic** by default: local DuckDB (`nexo_os/data/synthetic/nexo.duckdb`). Production data source is configurable: BigQuery, GCS, or Turso/libSQL. | PII in `clientes`/`leads` (see DATA_MODEL.md) |
| System data (`acciones`, `agent_runs`, `audit_log`) | Local DuckDB runtime store (`nexo_os/data/runtime/`, gitignored). Production: BigQuery, or Turso/libSQL (full backend, or `NEXO_SYSTEM_STORE=turso` hybrid — the hash-chained `audit_log` is stored there). | Identifiers + decisions; no full PII |
| User credentials | `config/users.json` (gitignored), bcrypt-hashed | Secret |
| Secrets (API key, BQ creds, cookie key) | `.env` (gitignored) / environment | Secret |

The committed synthetic dataset is clearly labelled synthetic and uses visibly
non-real PII (reserved `20-99xxxxxx-0` documents, `@example.com` emails, fake names).

## Authentication & authorization
- Real login for the broker's seats; passwords are **bcrypt-hashed**
  (`nexo_os/security/users.py`) and verified via `streamlit-authenticator`.
- No anonymous access — no dashboard page renders without a valid session.
- Sessions expire (`NEXO_AUTH_SESSION_MINUTES`).
- Roles: **admin** (sees all, manages users) and **operador** (operates the inbox +
  views). The Usuarios view is admin-only.
- **First-boot bootstrap** is the one allowed provisioning path:
  `python -m nexo_os bootstrap-admin` reads `NEXO_ADMIN_USERNAME` / `NEXO_ADMIN_PASSWORD`
  / `NEXO_ADMIN_NAME` from `.env`. It fails closed if no password is set and is
  idempotent. There is no anonymous fallback.

## What is sent to the model
- The model is used **only** to write Spanish prose, and **only** for the figures the
  deterministic core already computed.
- `narrate` receives the action's rationale (identifiers + numbers) and the
  deterministic facts — never full `documento`, `email`, `telefono`, or
  `fecha_nacimiento`. The PII registry (`schema_def.PII_FIELDS`) drives a redaction
  helper (`security/pii.py`); a client is identified to the model by id + first name.
- Every number in model prose is verified against the rationale by the grounding
  guardrail (`grounding.py`); ungrounded prose is rejected and replaced by the
  deterministic, grounded text. Eval suite 4 asserts no PII reaches narrate inputs.

## Audit trail
- `audit_log` is **append-only** (application code never updates/deletes) and
  **hash-chained**: each row's hash covers the previous row's hash plus its own
  fields. Tampering with any earlier row breaks every subsequent hash.
- This is tamper-**evidence**, not tamper-**prevention**: it lets you *detect* a break
  in the underlying store, it does not physically prevent one. Physical prevention
  requires database-level controls (append-only tables, IAM, immutability policies) at
  cutover.
- `verify_chain` confirms integrity; the Auditoría dashboard view shows it live.
- Audit detail payloads carry identifiers only — never full PII.

## Execution seam (human-driven by design)
- `security/execution.py` defines `ExecutionAdapter`; the active implementation,
  `NoopExecutionAdapter`, records a "would execute" event to the audit log and performs
  no external side effect. Approving an action records the decision and executes nothing
  outbound (no email/WhatsApp/SMS, no AMS/insurer write-back) — a deliberate control for
  a system that touches money.

## Fail-closed posture
- Missing data, a failed reconciliation, a low-confidence inference, or model prose
  that fails the grounding check results in a flagged/blocked item, never a guessed
  one. Runs report `error` rather than emitting partial numbers as if complete.

## Secrets hygiene
- All secrets via environment / `.env` (gitignored) and pydantic-settings.
- `.env.example` documents the keys with empty values. Nothing sensitive is committed.
- Use a dedicated Anthropic API key for Nexo (not shared with other projects).

## Retention stance
- Synthetic data is regenerable and disposable. In production, domain-data retention is
  governed by BigQuery; `audit_log` is retained indefinitely (append-only) as the
  record of who approved what and when.
