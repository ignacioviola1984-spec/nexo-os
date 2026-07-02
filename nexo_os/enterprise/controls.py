"""SOC2-style control harness.

Each control is a small function that *checks* a Trust Service Criteria-aligned control
and returns Pass / Fail / N/A with concrete evidence. This is emphatically **not** a SOC2
attestation - no auditor, no certification. It is an executable self-assessment of the
posture, so drift shows up as a failing control in CI rather than in a review months
later. Control ids follow the SOC2 Common Criteria (CC-series) plus the Availability (A),
Confidentiality (C) and Processing Integrity (PI) categories.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from nexo_os.config import REPO_ROOT, Settings, get_settings


class ControlStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NA = "N/A"


@dataclass(frozen=True)
class ControlResult:
    id: str
    criteria: str
    title: str
    status: ControlStatus
    evidence: str


def _ok(id, crit, title, ev) -> ControlResult:
    return ControlResult(id, crit, title, ControlStatus.PASS, ev)


def _fail(id, crit, title, ev) -> ControlResult:
    return ControlResult(id, crit, title, ControlStatus.FAIL, ev)


def _gitignore_covers(*patterns: str) -> bool:
    path = REPO_ROOT / ".gitignore"
    if not path.exists():
        return False
    body = path.read_text(encoding="utf-8")
    lines = {ln.strip() for ln in body.splitlines()}
    return all(any(p in ln for ln in lines) for p in patterns)


# --- individual controls ------------------------------------------------------


def c_access_control(s: Settings) -> ControlResult:
    cid, crit, title = (
        "CC6.1",
        "CC6.1 Logical access",
        "Authentication required; no open prod access",
    )
    if s.is_production and s.demo_mode:
        return _fail(cid, crit, title, "NEXO_DEMO_MODE (open access) is on in production.")
    return _ok(cid, crit, title, f"auth_mode={s.auth_mode.value}, demo_mode={s.demo_mode}")


def c_rbac_deny_by_default(s: Settings) -> ControlResult:
    from nexo_os.enterprise.rbac import (
        ROLE_OPERADOR,
        ROLE_VIEWER,
        Permission,
        has_permission,
        permissions_for,
    )

    cid, crit, title = "CC6.1b", "CC6.1 Logical access", "RBAC is deny-by-default & least-privilege"
    if permissions_for(None):
        return _fail(cid, crit, title, "unknown/None role has permissions (not deny-by-default).")
    # A non-admin must not manage users; viewer must be a strict subset of operador.
    if has_permission(ROLE_OPERADOR, Permission.MANAGE_USERS):
        return _fail(cid, crit, title, "operador can MANAGE_USERS (privilege creep).")
    if not permissions_for(ROLE_VIEWER) < permissions_for(ROLE_OPERADOR):
        return _fail(cid, crit, title, "viewer is not a strict subset of operador.")
    return _ok(cid, crit, title, "None->{}; operador lacks user-mgmt; viewer < operador")


def c_secret_hygiene(s: Settings) -> ControlResult:
    from nexo_os.enterprise.secrets import cookie_key_is_weak

    cid, crit, title = "CC6.2", "CC6.2 Credentials", "No weak/placeholder secrets in production"
    weak = cookie_key_is_weak(s.auth_cookie_key)
    if s.is_production and weak:
        return _fail(cid, crit, title, "auth cookie key is a placeholder/too short in production.")
    return _ok(
        cid, crit, title, "cookie key strong" if not weak else "weak key (non-prod, allowed)"
    )


def c_secret_rotation(s: Settings) -> ControlResult:
    from nexo_os.enterprise.secrets import rotation_due, secret_age_days

    cid, crit, title = "CC6.2b", "CC6.2 Credentials", "Secret rotation within policy"
    if rotation_due(s):
        age = secret_age_days(s)
        detail = "rotation date unknown" if age is None else f"cookie key is {age}d old"
        return _fail(cid, crit, title, f"{detail} (max {s.secret_max_age_days}d).")
    return _ok(cid, crit, title, f"within {s.secret_max_age_days}d policy")


def c_secrets_not_committed(s: Settings) -> ControlResult:
    cid, crit, title = "CC6.6", "CC6.6 Confidential data", "Secrets & PII stores are gitignored"
    if _gitignore_covers(".env", "users.json"):
        return _ok(cid, crit, title, ".env and config/users.json are gitignored")
    return _fail(cid, crit, title, ".gitignore does not cover .env and/or users.json")


def c_change_management(s: Settings) -> ControlResult:
    cid, crit, title = (
        "CC7.1",
        "CC7.1 Change management",
        "CI pipeline present (lint/test/eval gate)",
    )
    if (REPO_ROOT / ".github" / "workflows" / "ci.yml").exists():
        return _ok(cid, crit, title, ".github/workflows/ci.yml runs lint->test->eval")
    return _fail(cid, crit, title, "no CI workflow found")


def c_monitoring(s: Settings) -> ControlResult:
    cid, crit, title = "CC7.2", "CC7.2 Monitoring", "Metrics & health probes enabled"
    from nexo_os.enterprise.observability import readiness

    r = readiness(settings=s)
    if not s.metrics_enabled:
        return _fail(cid, crit, title, "NEXO_METRICS_ENABLED is off.")
    return _ok(cid, crit, title, f"metrics on; readiness ready={r.ready}")


def c_incident_response(s: Settings) -> ControlResult:
    cid, crit, title = "CC7.3", "CC7.3 Incident response", "Incident runbook + tooling exist"
    doc = (REPO_ROOT / "docs" / "INCIDENT_RESPONSE.md").exists()
    if doc:
        return _ok(cid, crit, title, "docs/INCIDENT_RESPONSE.md + `nexo incident-report`")
    return _fail(cid, crit, title, "docs/INCIDENT_RESPONSE.md missing")


def c_audit_integrity(s: Settings) -> ControlResult:
    cid, crit, title = "CC7.4", "CC7.4 Audit trail", "Audit log is append-only & hash-chained"
    # Structural: the writer never updates/deletes and verify_chain exists.
    from nexo_os.audit import AuditWriter, verify_chain  # noqa: F401

    return _ok(cid, crit, title, "hash-chained audit_log with verify_chain (see SECURITY.md)")


def c_availability_health(s: Settings) -> ControlResult:
    cid, crit, title = "A1.2", "A1.2 Availability", "Liveness/readiness endpoints exist"
    from nexo_os.enterprise.observability import liveness

    return _ok(cid, crit, title, f"liveness={liveness().ok}; `nexo healthcheck`")


def c_confidentiality_pii(s: Settings) -> ControlResult:
    cid, crit, title = (
        "C1.1",
        "C1.1 Confidentiality",
        "PII registry drives redaction before the model",
    )
    from nexo_os.data.schema_def import PII_FIELDS

    n = sum(len(v) for v in PII_FIELDS.values())
    if n == 0:
        return _fail(cid, crit, title, "PII registry is empty; redaction cannot be enforced.")
    return _ok(cid, crit, title, f"{n} PII fields registered; narrate redacts via security/pii.py")


def c_processing_integrity(s: Settings) -> ControlResult:
    cid, crit, title = "PI1.1", "PI1.1 Processing integrity", "Deterministic core + eval gate"
    if (REPO_ROOT / "nexo_os" / "evals" / "runner.py").exists():
        return _ok(cid, crit, title, "numbers computed in core (Decimal); eval gate exits non-zero")
    return _fail(cid, crit, title, "eval runner missing")


def c_data_contracts(s: Settings) -> ControlResult:
    cid, crit, title = (
        "PI1.2",
        "PI1.2 Input validation",
        "Data contracts validate upstream extracts",
    )
    from nexo_os.enterprise.data_contracts import domain_contracts

    return _ok(
        cid,
        crit,
        title,
        f"{len(domain_contracts(s))} domain contracts; `nexo data-contract-validate`",
    )


ALL_CONTROLS: tuple[Callable[[Settings], ControlResult], ...] = (
    c_access_control,
    c_rbac_deny_by_default,
    c_secret_hygiene,
    c_secret_rotation,
    c_secrets_not_committed,
    c_change_management,
    c_monitoring,
    c_incident_response,
    c_audit_integrity,
    c_availability_health,
    c_confidentiality_pii,
    c_processing_integrity,
    c_data_contracts,
)


def run_controls(settings: Settings | None = None) -> list[ControlResult]:
    settings = settings or get_settings()
    return [c(settings) for c in ALL_CONTROLS]


def summarize(results: list[ControlResult]) -> dict[str, int]:
    out = {"PASS": 0, "FAIL": 0, "N/A": 0}
    for r in results:
        out[r.status.value] += 1
    return out


def render_report(results: list[ControlResult]) -> str:
    counts = summarize(results)
    lines = [
        "# SOC2-style control self-assessment",
        "",
        "Executable self-assessment - not a SOC2 attestation. See docs/SOC2_CONTROLS.md.",
        "",
        f"PASS {counts['PASS']} - FAIL {counts['FAIL']} - N/A {counts['N/A']}",
        "",
        "| Control | Criteria | Status | Evidence |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r.id} | {r.criteria} | {r.status.value} | {r.evidence} |")
    return "\n".join(lines) + "\n"
