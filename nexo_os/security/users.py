"""User store and bootstrap. Credentials are bcrypt-hashed and stored in a gitignored
JSON file (config/users.json). The first admin is provisioned once from .env via
`python -m nexo_os bootstrap-admin` — the only allowed bootstrap; there is no
anonymous fallback.

Roles are defined canonically in `enterprise.rbac`: 'admin' (sees all, manages users),
'operador' (operates the inbox + views), plus least-privilege 'auditor' (reads the
audit trail + numbers) and 'viewer' (reads the numbers only).
"""

from __future__ import annotations

import json
from pathlib import Path

import bcrypt

from nexo_os.config import get_settings
from nexo_os.enterprise.rbac import (
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_OPERADOR,
    ROLE_VIEWER,
    VALID_ROLES,
)
from nexo_os.logging_setup import get_logger

log = get_logger("users")

# Re-exported so existing imports (`user_store.ROLE_ADMIN`, etc.) keep working while
# rbac.py remains the single source of truth for the role set.
__all__ = [
    "ROLE_ADMIN",
    "ROLE_OPERADOR",
    "ROLE_AUDITOR",
    "ROLE_VIEWER",
    "VALID_ROLES",
    "hash_password",
    "verify_password",
    "load_users",
    "save_users",
    "add_user",
    "get_role",
    "to_authenticator_credentials",
    "bootstrap_admin",
]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def _users_path() -> Path:
    return get_settings().users_path


def load_users() -> dict:
    path = _users_path()
    if not path.exists():
        return {"usernames": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_users(users: dict) -> None:
    path = _users_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(users, indent=2, ensure_ascii=False), encoding="utf-8")


def add_user(username: str, name: str, password: str, role: str, email: str = "") -> None:
    if role not in VALID_ROLES:
        raise ValueError(f"Rol inválido: {role}")
    users = load_users()
    users.setdefault("usernames", {})[username] = {
        "name": name,
        "password": hash_password(password),
        "role": role,
        "email": email,
    }
    save_users(users)


def get_role(username: str) -> str | None:
    return load_users().get("usernames", {}).get(username, {}).get("role")


def to_authenticator_credentials() -> dict:
    """Shape expected by streamlit-authenticator (pre-hashed passwords)."""
    users = load_users().get("usernames", {})
    return {
        "usernames": {
            u: {
                "name": info["name"],
                "password": info["password"],
                "email": info.get("email", ""),
                "roles": [info.get("role", ROLE_OPERADOR)],
            }
            for u, info in users.items()
        }
    }


def bootstrap_admin() -> int:
    """Provision the initial admin from .env. Idempotent: does nothing if the user
    already exists. Fails closed if no password is configured."""
    settings = get_settings()
    if not settings.admin_password:
        print(
            "bootstrap-admin: NEXO_ADMIN_PASSWORD is not set in .env. Failing closed.",
        )
        return 1
    users = load_users()
    if settings.admin_username in users.get("usernames", {}):
        print(f"bootstrap-admin: user '{settings.admin_username}' already exists. Nothing to do.")
        return 0
    add_user(
        username=settings.admin_username,
        name=settings.admin_name,
        password=settings.admin_password,
        role=ROLE_ADMIN,
    )
    log.info("bootstrap_admin.created", username=settings.admin_username)
    print(f"bootstrap-admin: created admin '{settings.admin_username}'.")
    return 0
