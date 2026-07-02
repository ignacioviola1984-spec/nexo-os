"""Full role-based access control.

Deny-by-default: a role has exactly the permissions granted to it in
``ROLE_PERMISSIONS`` and nothing else. Every guarded operation calls ``require`` (which
raises ``PermissionDenied``) or checks ``has_permission``; the dashboard hides what a
seat cannot do and the enforcement functions block it even if the UI is bypassed.

This module is the single source of truth for roles - ``security/users.py`` imports the
role constants from here, so there is one canonical set. The two original roles
(``admin``, ``operador``) keep their exact former meaning; ``auditor`` and ``viewer``
are added for least-privilege separation (read the audit trail / read the numbers,
without the ability to resolve inbox items or manage users).
"""

from __future__ import annotations

from enum import StrEnum

# --- roles (canonical) --------------------------------------------------------
ROLE_ADMIN = "admin"
ROLE_OPERADOR = "operador"
ROLE_AUDITOR = "auditor"
ROLE_VIEWER = "viewer"

ALL_ROLES: tuple[str, ...] = (ROLE_ADMIN, ROLE_OPERADOR, ROLE_AUDITOR, ROLE_VIEWER)
VALID_ROLES: set[str] = set(ALL_ROLES)


class Permission(StrEnum):
    """Granular, checkable capabilities. Views and mutating actions are separate so a
    read-only seat can never resolve an action or manage a user."""

    VIEW_DASHBOARD = "view_dashboard"
    VIEW_PORTFOLIO = "view_portfolio"
    VIEW_METRICS = "view_metrics"
    VIEW_AUDIT = "view_audit"
    INBOX_VIEW = "inbox_view"
    INBOX_RESOLVE = "inbox_resolve"  # approve / reject / edit an action (HITL)
    RUN_ORCHESTRATION = "run_orchestration"
    EXPORT_DATA = "export_data"
    MANAGE_USERS = "manage_users"
    RUN_SECURITY_TOOLS = "run_security_tools"  # controls-check / security-review / incident


# --- role -> permissions (deny-by-default) ------------------------------------
_ADMIN_PERMS = frozenset(Permission)  # admin holds every permission

ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    ROLE_ADMIN: _ADMIN_PERMS,
    ROLE_OPERADOR: frozenset(
        {
            Permission.VIEW_DASHBOARD,
            Permission.VIEW_PORTFOLIO,
            Permission.VIEW_METRICS,
            Permission.VIEW_AUDIT,
            Permission.INBOX_VIEW,
            Permission.INBOX_RESOLVE,
            Permission.RUN_ORCHESTRATION,
            Permission.EXPORT_DATA,
        }
    ),
    ROLE_AUDITOR: frozenset(
        {
            Permission.VIEW_DASHBOARD,
            Permission.VIEW_METRICS,
            Permission.VIEW_AUDIT,
            Permission.INBOX_VIEW,  # read-only visibility into the inbox
            Permission.EXPORT_DATA,
            Permission.RUN_SECURITY_TOOLS,
        }
    ),
    ROLE_VIEWER: frozenset(
        {
            Permission.VIEW_DASHBOARD,
            Permission.VIEW_PORTFOLIO,
            Permission.VIEW_METRICS,
        }
    ),
}


class PermissionDenied(PermissionError):
    """Raised when a role lacks a required permission. Carries the role and permission
    so the audit log records exactly what was refused."""

    def __init__(self, role: str | None, permission: Permission) -> None:
        self.role = role
        self.permission = permission
        super().__init__(f"Rol '{role or 'sin-rol'}' no tiene permiso '{permission.value}'.")


def permissions_for(role: str | None) -> frozenset[Permission]:
    """The permission set for a role. Unknown/None role -> empty set (deny-by-default)."""
    return ROLE_PERMISSIONS.get(role or "", frozenset())


def has_permission(role: str | None, permission: Permission) -> bool:
    return permission in permissions_for(role)


def require(role: str | None, permission: Permission) -> None:
    """Enforce a permission. Raises ``PermissionDenied`` when the role lacks it."""
    if not has_permission(role, permission):
        raise PermissionDenied(role, permission)


def is_valid_role(role: str) -> bool:
    return role in VALID_ROLES
