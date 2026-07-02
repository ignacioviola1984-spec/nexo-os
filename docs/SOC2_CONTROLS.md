# SOC2-style control matrix

This is an **executable self-assessment**, not a SOC2 attestation. There is no auditor
and no report. `nexo controls-check` runs each control as code and prints Pass / Fail /
N/A with evidence, so posture drift shows up as a failing control in CI instead of in a
review months later. Control ids follow the SOC2 Common Criteria (CC-series) plus the
Availability (A), Confidentiality (C) and Processing Integrity (PI) categories.

Run it:

```bash
python -m nexo_os controls-check   # exits non-zero on any FAIL
```

## Controls

| Control | Trust criteria | What is checked | How |
|---|---|---|---|
| CC6.1 | Logical access | Authentication required; no open access in production | `demo_mode` off when `NEXO_ENV=production` |
| CC6.1b | Logical access | RBAC is deny-by-default and least-privilege | unknown role -> no perms; operador lacks user-mgmt; viewer strict subset of operador |
| CC6.2 | Credentials | No weak/placeholder secrets in production | `cookie_key_is_weak` false in prod |
| CC6.2b | Credentials | Secret rotation within policy | cookie key age <= `NEXO_SECRET_MAX_AGE_DAYS` |
| CC6.6 | Confidential data | Secret and PII stores are gitignored | `.gitignore` covers `.env`, `config/users.json` |
| CC7.1 | Change management | CI pipeline present | `.github/workflows/ci.yml` runs lint -> test -> eval |
| CC7.2 | Monitoring | Metrics and health probes enabled | `NEXO_METRICS_ENABLED` on; readiness ready |
| CC7.3 | Incident response | Runbook and tooling exist | this repo + `nexo incident-report` |
| CC7.4 | Audit trail | Audit log is append-only and hash-chained | `verify_chain`; see SECURITY.md |
| A1.2 | Availability | Liveness/readiness endpoints exist | `nexo healthcheck` |
| C1.1 | Confidentiality | PII registry drives redaction before the model | `schema_def.PII_FIELDS` non-empty |
| PI1.1 | Processing integrity | Deterministic core + eval gate | numbers in core (Decimal); eval exits non-zero |
| PI1.2 | Input validation | Data contracts validate upstream extracts | `nexo data-contract-validate` |

## What a real SOC2 program would add on top

The items below are organizational, not code, and are out of scope for this repository:

- An independent auditor and a Type I/II report over a defined observation window.
- Vendor/subprocessor management, HR controls (background checks, onboarding/offboarding),
  and formal risk assessments.
- Cloud-provider infrastructure controls (physical security, backup/restore drills,
  encryption-at-rest key management) evidenced from the hosting environment.

The harness here gives the engineering-side evidence those programs consume; it does not
replace them.
