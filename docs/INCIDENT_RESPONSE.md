# Incident response runbook

For a system that touches money and PII, the first job in an incident is a trustworthy
snapshot of state, and to put the response itself on the record. `nexo incident-report`
captures the snapshot (audit-chain integrity, last run status, readiness, metrics) and
records the incident to the hash-chained audit log.

```bash
python -m nexo_os incident-report --severity SEV1 --summary "audit chain verify failed" --actor nacho
```

## Severities

| Sev | Meaning | Target response |
|---|---|---|
| SEV1 | Broker cannot operate, audit-integrity break, or suspected data exposure | Immediate |
| SEV2 | Major function degraded, no clean workaround | Same day |
| SEV3 | Minor or partial degradation, workaround exists | Next business day |
| SEV4 | Cosmetic / informational | Backlog |

## Roles

- **Incident commander** - owns the response, decides severity, runs comms. Default: the
  on-call operator or the admin.
- **Scribe** - the audit log is the primary scribe (every resolution and the incident
  open event are recorded immutably). Human notes go in the incident channel.

## First 15 minutes

1. Run `nexo incident-report` with your best-guess severity. Paste the rendered report
   into the incident channel.
2. Read the snapshot:
   - **Audit chain BROKEN** -> treat as SEV1. Do not mutate the store. The break index
     points at the first tampered/lost row. Preserve the store for forensics.
   - **Readiness NOT ready** -> check which probe failed (data source, secret hygiene).
   - **Last run estado = error** -> the orchestrator failed closed; no partial numbers
     were emitted (by design). Inspect `agent_runs.resumen_json`.
3. Decide: mitigate in place, or roll back.

## Rollback decision

Run `nexo rollback-check <target-manifest.json>` (see [DEPLOYMENT.md](DEPLOYMENT.md)). It
blocks a rollback across a schema change (fingerprint mismatch) because that needs a
down-migration first. Only roll back when the check says SAFE.

## Containment specifics

- **Suspected credential compromise** -> `nexo rotate-secret cookie`, set the new `.env`
  values, redeploy. The previous key stays valid during the grace window so live
  sessions are not dropped; clear `NEXO_AUTH_COOKIE_KEY_PREVIOUS` after.
- **Suspected data-source issue** -> the source is a single seam
  (`get_repository()`); the synthetic backend is a known-good fallback for triage. Never
  fabricate data to "keep it up" - the system is designed to fail closed.

## After

- Confirm `nexo controls-check` and `nexo security-review` are green.
- Write a short post-incident note (what broke, blast radius, fix, follow-ups). The audit
  log already holds the immutable timeline.
