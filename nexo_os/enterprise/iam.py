"""Cloud IAM: map an external identity provider's group memberships to Nexo roles.

Federated identity (SSO) authenticates *who* the user is; IAM decides *what* they may
do by binding IdP groups (or a cloud IAM policy's principals) to Nexo roles. Bindings
are configured as JSON - inline (``NEXO_IAM_ROLE_BINDINGS``) or a file
(``NEXO_IAM_BINDINGS_PATH``) - e.g. ``{"nexo-admins": "admin", "nexo-ops": "operador"}``.

Deny-by-default: a federated user whose groups match no binding gets no role unless an
explicit ``NEXO_IAM_DEFAULT_ROLE`` is set. When a user matches several bindings, the
most-privileged role wins (admin > operador > auditor > viewer).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from nexo_os.config import Settings, get_settings
from nexo_os.enterprise.rbac import (
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_OPERADOR,
    ROLE_VIEWER,
    VALID_ROLES,
)

# Highest privilege first; used to pick a single role when several match.
_ROLE_PRECEDENCE = (ROLE_ADMIN, ROLE_OPERADOR, ROLE_AUDITOR, ROLE_VIEWER)


class IAMConfigError(ValueError):
    """The IAM bindings are malformed or reference an unknown role. Fail closed."""


def load_bindings(settings: Settings | None = None) -> dict[str, str]:
    """Parse and validate the group->role bindings. Empty when none configured."""
    settings = settings or get_settings()
    raw: str | None = None
    if settings.iam_role_bindings:
        raw = settings.iam_role_bindings
    elif settings.iam_bindings_path:
        path = settings.iam_bindings_path
        if not path.exists():
            raise IAMConfigError(f"IAM bindings file not found: {path}")
        raw = path.read_text(encoding="utf-8")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IAMConfigError(f"IAM bindings are not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise IAMConfigError("IAM bindings must be a JSON object {group: role}.")
    bindings: dict[str, str] = {}
    for group, role in data.items():
        if role not in VALID_ROLES:
            raise IAMConfigError(
                f"IAM binding '{group}' -> '{role}': unknown role. "
                f"Valid roles: {sorted(VALID_ROLES)}."
            )
        bindings[str(group)] = str(role)
    return bindings


def validate_bindings(settings: Settings | None = None) -> list[str]:
    """Return a list of human-readable problems (empty when valid). Never raises."""
    settings = settings or get_settings()
    problems: list[str] = []
    try:
        bindings = load_bindings(settings)
    except IAMConfigError as exc:
        return [str(exc)]
    if settings.iam_default_role and settings.iam_default_role not in VALID_ROLES:
        problems.append(f"NEXO_IAM_DEFAULT_ROLE '{settings.iam_default_role}' is not a valid role.")
    if not bindings and not settings.iam_default_role:
        problems.append("IAM has no bindings and no default role: every federated user is denied.")
    return problems


@dataclass(frozen=True)
class RoleResolution:
    role: str | None
    matched_groups: list[str]
    via_default: bool


def resolve_roles(groups: list[str], settings: Settings | None = None) -> list[str]:
    """All Nexo roles a set of IdP groups maps to (deduplicated)."""
    bindings = load_bindings(settings)
    seen: list[str] = []
    for g in groups:
        role = bindings.get(g)
        if role and role not in seen:
            seen.append(role)
    return seen


def resolve_primary_role(groups: list[str], settings: Settings | None = None) -> RoleResolution:
    """Pick the single effective role for a federated user: the most-privileged
    matched role, else the configured default, else None (denied)."""
    settings = settings or get_settings()
    bindings = load_bindings(settings)
    matched = [g for g in groups if g in bindings]
    roles = {bindings[g] for g in matched}
    for role in _ROLE_PRECEDENCE:
        if role in roles:
            return RoleResolution(role=role, matched_groups=matched, via_default=False)
    if settings.iam_default_role:
        return RoleResolution(role=settings.iam_default_role, matched_groups=[], via_default=True)
    return RoleResolution(role=None, matched_groups=[], via_default=False)
