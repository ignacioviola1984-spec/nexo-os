# Enterprise security review

`nexo security-review` is an automated pre-cutover / pre-release scan. It composes the
SOC2 control harness with the checks a reviewer runs by hand and produces
severity-ranked findings. It exits non-zero when any finding is HIGH or CRITICAL, so it
can gate a deploy.

```bash
NEXO_ENV=production python -m nexo_os security-review   # non-zero on HIGH/CRITICAL
```

It reports the gaps it can detect. It does not assert the system is secure.

## Checks

| id | Severity (prod) | Detects |
|---|---|---|
| SEC-001 | CRITICAL | Weak / placeholder auth cookie key |
| SEC-002 | CRITICAL | Open access (`demo_mode`) in production |
| SEC-003 | HIGH | `.env` / `config/users.json` not clearly gitignored |
| SEC-004 | MEDIUM | Core dependencies without an exact pin |
| SEC-005 | HIGH | OIDC selected but issuer/client id missing |
| SEC-006 | MEDIUM | OIDC trusts proxy-forwarded claims (only safe behind a verifying proxy) |
| SEC-007 | HIGH | IAM bindings malformed or leave users with no role |
| SEC-008 | HIGH | Auth secret past its rotation policy |
| SEC-009 | CRITICAL | PII registry empty (redaction cannot be enforced) |

Severity for some findings is lower outside production (for example, a weak key in `dev`
is MEDIUM, not CRITICAL) so local development is not blocked while production is held to
the strict bar.

## Manual review checklist (beyond the automated scan)

- Confirm the hosting platform encrypts data at rest and in transit, and that backups are
  tested.
- Confirm least-privilege on cloud IAM for the service account (BigQuery/GCS/Turso).
- Confirm the OIDC IdP enforces MFA and that group membership is the source of truth for
  the IAM bindings.
- Confirm log retention and that logs never carry PII (the code redacts; verify the sink
  does not re-introduce it).
- Review the disabled execution seam before any future enablement of outbound actions.
