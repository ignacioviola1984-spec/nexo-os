"""Enterprise / production-hardening layer.

This package adds the controls an enterprise buyer's security review asks for, on top
of the deterministic HITL core. Each concern is real, executable code and follows the
same honesty register as the rest of Nexo:

- Things that run and are enforced now: RBAC (`rbac`), observability + health
  (`observability`), data contracts (`data_contracts`), secret rotation + hygiene
  (`secrets`), the SOC2-style control harness (`controls`), the automated security
  review (`security_review`), and incident response (`incident`).
- Seams that are code-real but fail closed until their external system is configured,
  exactly like the data-source and execution seams: SSO/OIDC (`sso`) and cloud IAM
  (`iam`).

Nothing here claims a certification. `controls` and `security_review` *check* the
posture and report Pass/Fail/NA with evidence; they do not assert compliance.
"""

from __future__ import annotations
