"""Automated enterprise security review.

A pre-cutover / pre-release scan that produces severity-ranked findings. It composes
the SOC2 control harness with additional checks a security reviewer runs by hand:
secret strength, open-access flags, dependency pinning, SSO/IAM configuration sanity,
rotation age, and PII-redaction presence. ``nexo security-review`` exits non-zero when
any finding is HIGH or CRITICAL, so it can gate a deploy.

Findings describe what is wrong and how to fix it. Nothing here asserts the system *is*
secure - it reports the gaps it can detect.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from enum import IntEnum

from nexo_os.config import REPO_ROOT, Settings, get_settings


class Severity(IntEnum):
    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return self.name


@dataclass(frozen=True)
class Finding:
    id: str
    severity: Severity
    title: str
    detail: str
    remediation: str


def _weak_secret(s: Settings) -> list[Finding]:
    from nexo_os.enterprise.secrets import cookie_key_is_weak

    if not cookie_key_is_weak(s.auth_cookie_key):
        return []
    sev = Severity.CRITICAL if s.is_production else Severity.MEDIUM
    return [
        Finding(
            "SEC-001",
            sev,
            "Weak auth cookie key",
            "NEXO_AUTH_COOKIE_KEY is a placeholder or shorter than 32 chars.",
            "Set a strong random key: `python -m nexo_os rotate-secret cookie`.",
        )
    ]


def _open_access(s: Settings) -> list[Finding]:
    if s.is_production and s.demo_mode:
        return [
            Finding(
                "SEC-002",
                Severity.CRITICAL,
                "Open access in production",
                "NEXO_DEMO_MODE=on disables authentication, but NEXO_ENV=production.",
                "Set NEXO_DEMO_MODE=off in production.",
            )
        ]
    return []


def _gitignore(s: Settings) -> list[Finding]:
    from nexo_os.enterprise.controls import _gitignore_covers

    if _gitignore_covers(".env", "users.json"):
        return []
    return [
        Finding(
            "SEC-003",
            Severity.HIGH,
            "Secret/PII stores may be committable",
            ".gitignore does not clearly cover .env and config/users.json.",
            "Add `.env` and `config/users.json` to .gitignore.",
        )
    ]


def _dependency_pinning(s: Settings) -> list[Finding]:
    pyproject = REPO_ROOT / "pyproject.toml"
    if not pyproject.exists():
        return []
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    deps = data.get("project", {}).get("dependencies", [])
    unpinned = [d for d in deps if "==" not in d]
    if not unpinned:
        return []
    return [
        Finding(
            "SEC-004",
            Severity.MEDIUM,
            "Unpinned core dependencies",
            f"Core deps without an exact pin: {', '.join(unpinned)}.",
            "Pin every runtime dependency with == for reproducible, auditable builds.",
        )
    ]


def _sso_config(s: Settings) -> list[Finding]:
    from nexo_os.config import AuthMode

    if s.auth_mode != AuthMode.oidc:
        return []
    findings: list[Finding] = []
    if not (s.oidc_issuer and s.oidc_client_id):
        findings.append(
            Finding(
                "SEC-005",
                Severity.HIGH,
                "OIDC selected but not configured",
                "NEXO_AUTH_MODE=oidc without issuer/client id - logins fail closed.",
                "Set NEXO_OIDC_ISSUER and NEXO_OIDC_CLIENT_ID, or use password mode.",
            )
        )
    if s.oidc_trust_proxy_claims:
        findings.append(
            Finding(
                "SEC-006",
                Severity.MEDIUM,
                "OIDC trusts proxy-forwarded claims",
                "NEXO_OIDC_TRUST_PROXY_CLAIMS=true: ID-token signatures are not verified "
                "in-process; this is only safe behind a verifying identity-aware proxy.",
                "Confirm an IAP/oauth2-proxy verifies tokens, or install [sso] and verify locally.",
            )
        )
    return findings


def _iam_config(s: Settings) -> list[Finding]:
    from nexo_os.config import AuthMode
    from nexo_os.enterprise.iam import validate_bindings

    if s.auth_mode != AuthMode.oidc:
        return []
    problems = validate_bindings(s)
    return [
        Finding(
            "SEC-007",
            Severity.HIGH,
            "IAM role bindings problem",
            p,
            "Fix NEXO_IAM_ROLE_BINDINGS / NEXO_IAM_BINDINGS_PATH so federated users get a role.",
        )
        for p in problems
    ]


def _rotation(s: Settings) -> list[Finding]:
    from nexo_os.enterprise.secrets import rotation_due, secret_age_days

    if not rotation_due(s):
        return []
    age = secret_age_days(s)
    sev = Severity.HIGH if s.is_production else Severity.LOW
    detail = (
        "rotation date unknown" if age is None else f"{age}d old (max {s.secret_max_age_days}d)"
    )
    return [
        Finding(
            "SEC-008",
            sev,
            "Secret past rotation policy",
            f"The auth cookie key is {detail}.",
            "Rotate: `python -m nexo_os rotate-secret cookie` and record NEXO_AUTH_COOKIE_KEY_ROTATED_ON.",
        )
    ]


def _pii_redaction(s: Settings) -> list[Finding]:
    from nexo_os.data.schema_def import PII_FIELDS

    if sum(len(v) for v in PII_FIELDS.values()) > 0:
        return []
    return [
        Finding(
            "SEC-009",
            Severity.CRITICAL,
            "PII registry empty",
            "No fields are marked PII, so redaction before the model cannot be enforced.",
            "Restore PII flags in schema_def; eval suite 4 must assert no PII reaches narrate.",
        )
    ]


_CHECKS = (
    _weak_secret,
    _open_access,
    _gitignore,
    _dependency_pinning,
    _sso_config,
    _iam_config,
    _rotation,
    _pii_redaction,
)


def run_security_review(settings: Settings | None = None) -> list[Finding]:
    settings = settings or get_settings()
    findings: list[Finding] = []
    for check in _CHECKS:
        findings.extend(check(settings))
    return sorted(findings, key=lambda f: (-int(f.severity), f.id))


def gate(findings: list[Finding], threshold: Severity = Severity.HIGH) -> bool:
    """True if the review passes (no finding at or above ``threshold``)."""
    return not any(f.severity >= threshold for f in findings)


def render_report(findings: list[Finding]) -> str:
    if not findings:
        return "# Security review\n\nNo findings. Posture checks passed.\n"
    lines = ["# Security review", "", f"{len(findings)} finding(s):", ""]
    for f in findings:
        lines.append(f"## [{f.severity.label}] {f.id} - {f.title}")
        lines.append(f"- {f.detail}")
        lines.append(f"- Fix: {f.remediation}")
        lines.append("")
    return "\n".join(lines)
