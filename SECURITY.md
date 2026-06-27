# Security & data handling

> Phase 0 stub — expanded in Phase 9. This single-tenant system touches money
> (premiums, commissions, collections) and client PII. Treat it accordingly.

## Authentication & authorization
- Real login for the broker's seats (bcrypt-hashed credentials). No anonymous access.
- Roles: `admin` (sees all, manages users) and `operador` (operates the inbox + views).
- First boot is provisioned once via `python -m nexo_os bootstrap-admin` from `.env`.

## PII
- PII fields are flagged in the canonical schema (`DATA_MODEL.md`): names, documents
  (CUIT/DNI), birth dates, emails, phones.
- The language model receives **only** what a message needs, via a redaction helper —
  never full documents, emails, phones, or birth dates.
- Logs and `audit_log` detail carry **identifiers only**, never full PII.
- Synthetic PII is visibly non-real (`@example.com`, reserved document ranges).

## Audit trail
- `audit_log` is append-only and **hash-chained** (each row hashes over the prior
  row's hash). This is tamper-**evidence**, not tamper-prevention: it lets you detect
  a break in the underlying store, it does not physically prevent one.

## Execution seam (disabled)
- An `ExecutionAdapter` interface exists with a single `NoopExecutionAdapter` that
  only records "would execute" to the audit log. Nothing is wired live: approving an
  action sends nothing in this build.

## Secrets
- All secrets via environment / `.env` (gitignored) and pydantic-settings. Nothing
  sensitive is committed. `.env.example` documents the keys.
