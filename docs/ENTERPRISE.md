# Enterprise / production hardening

The controls an enterprise security review asks for, added on top of the deterministic
HITL core. Every item is real, executable code. This document maps the twelve concerns
to what runs, and states honestly what is enforced now vs. what is a fail-closed seam
that activates at cutover.

Nothing here is a certification. The control harness and security review *check* the
posture and report Pass / Fail / finding; they do not assert compliance.

## Status legend

- **Enforced** - runs and blocks in this codebase now.
- **Seam (fail-closed)** - real code that activates when its external system is
  configured, and refuses to run insecurely otherwise. Same posture as the existing
  data-source and execution seams.
- **Runbook + tooling** - a documented process plus a command that produces evidence.

## The twelve

| # | Concern | Where | Status |
|---|---|---|---|
| 1 | Full RBAC | `enterprise/rbac.py`; enforced in `review.resolve_accion` + dashboard nav | Enforced |
| 2 | SSO (OIDC) | `enterprise/sso.py` (`NEXO_AUTH_MODE=oidc`) | Seam (fail-closed) |
| 3 | Cloud IAM | `enterprise/iam.py` (group -> role bindings) | Seam (fail-closed) |
| 4 | Production observability | `enterprise/observability.py` (metrics, health, readiness) | Enforced |
| 5 | Incident response | `enterprise/incident.py` + [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) | Runbook + tooling |
| 6 | Deployment pipelines | `.github/workflows/deploy.yml` + [DEPLOYMENT.md](DEPLOYMENT.md) | Runbook + tooling |
| 7 | Data contracts (ERP/AMS) | `enterprise/data_contracts.py`; `nexo data-contract-validate` | Enforced |
| 8 | Monitoring | `enterprise/observability.py` metrics + [OBSERVABILITY.md](OBSERVABILITY.md) | Enforced |
| 9 | Secrets rotation | `enterprise/secrets.py`; `nexo rotate-secret` | Enforced |
| 10 | Production rollback | `enterprise/release.py`; `nexo rollback-check` | Enforced |
| 11 | Enterprise security review | `enterprise/security_review.py`; `nexo security-review` | Enforced |
| 12 | SOC2-level controls | `enterprise/controls.py`; `nexo controls-check` + [SOC2_CONTROLS.md](SOC2_CONTROLS.md) | Runbook + tooling |

## Commands

| Command | What it does | Exit |
|---|---|---|
| `nexo healthcheck` | Liveness/readiness probe (JSON) | non-zero when not ready |
| `nexo controls-check` | SOC2-style control self-assessment | non-zero on any FAIL |
| `nexo security-review` | Automated security review | non-zero on HIGH/CRITICAL |
| `nexo data-contract-validate` | Validate the active domain source vs the data contracts | non-zero on violation |
| `nexo rotate-secret cookie` | Print a cookie-key rotation plan (writes nothing) | 0 |
| `nexo iam-validate` | Validate the IAM group->role bindings | non-zero on problem |
| `nexo incident-report` | Snapshot state + record an incident to the audit log | 0 |
| `nexo release-manifest` | Print/write the current release manifest | 0 |
| `nexo rollback-check <manifest>` | Is rolling back to that release safe? | non-zero when blocked |

## Design rules kept

- **Deny-by-default.** An unknown role has no permissions; a federated user matched by
  no IAM binding gets no role unless an explicit default is set.
- **Fail closed.** Selecting OIDC / a cloud secret manager without its configuration
  raises; it never silently downgrades to open access.
- **No new numbers.** None of this touches how figures are computed. The deterministic
  core, the grounding wall, and the HITL inbox are unchanged.
- **Single-tenant by isolation** stays true: IAM/SSO federate identity into one
  tenant's seats; they do not add multi-tenant data sharing.
