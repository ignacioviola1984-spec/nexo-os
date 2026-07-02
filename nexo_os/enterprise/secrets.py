"""Secrets management and rotation.

Two concerns:

1. **Sourcing.** ``SecretProvider`` abstracts where a runtime secret comes from. The
   default ``EnvSecretProvider`` reads process env / ``.env`` (the existing behavior).
   ``gcp`` / ``aws`` / ``vault`` are cloud secret-manager seams: real classes that fail
   closed (raise) when selected without their client library and configuration - the
   same posture as the data-source seams.

2. **Rotation.** The Streamlit auth cookie key can be rotated without force-logging-out
   live sessions: the previous key is kept valid during a grace window
   (``active_cookie_keys``). ``plan_cookie_key_rotation`` generates a strong new key and
   returns the exact ``.env`` values to set; ``rotation_due`` and ``secret_age_days``
   drive the security-review warning when a key is past ``NEXO_SECRET_MAX_AGE_DAYS``.
"""

from __future__ import annotations

import secrets as pysecrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from nexo_os.config import SecretManager, Settings, get_settings

# Values that must never appear as a real secret (the documented placeholders).
WEAK_COOKIE_KEYS = {"", "change-me", "change-me-to-a-random-secret"}
MIN_COOKIE_KEY_LEN = 32


def cookie_key_is_weak(key: str | None) -> bool:
    """A cookie key is weak if it is a documented placeholder or too short to resist
    offline attack on the session cookie."""
    if key is None:
        return True
    return key.strip() in WEAK_COOKIE_KEYS or len(key.strip()) < MIN_COOKIE_KEY_LEN


def generate_key(nbytes: int = 48) -> str:
    """A cryptographically strong, URL-safe secret."""
    return pysecrets.token_urlsafe(nbytes)


def active_cookie_keys(settings: Settings | None = None) -> list[str]:
    """Cookie keys that should be accepted right now: the primary, plus the previous
    key while a rotation grace window is open (so existing sessions are not dropped)."""
    settings = settings or get_settings()
    keys = [settings.auth_cookie_key]
    prev = settings.auth_cookie_key_previous
    if prev and prev != settings.auth_cookie_key:
        keys.append(prev)
    return keys


def secret_age_days(settings: Settings | None = None, today: date | None = None) -> int | None:
    """Days since the cookie key was last rotated, or None if unknown."""
    settings = settings or get_settings()
    if settings.auth_cookie_key_rotated_on is None:
        return None
    from nexo_os.clock import now

    ref = today or now().date()
    return (ref - settings.auth_cookie_key_rotated_on).days


def rotation_due(settings: Settings | None = None, today: date | None = None) -> bool:
    """True when the cookie key is older than the configured max age, or its age is
    unknown while running in production (fail-closed: treat unknown as overdue)."""
    settings = settings or get_settings()
    age = secret_age_days(settings, today)
    if age is None:
        return settings.is_production
    return age > settings.secret_max_age_days


@dataclass(frozen=True)
class RotationPlan:
    new_key: str
    previous_key: str
    rotated_on: date
    env_lines: dict[str, str]

    def render(self) -> str:
        return "\n".join(f"{k}={v}" for k, v in self.env_lines.items())


def plan_cookie_key_rotation(
    settings: Settings | None = None, today: date | None = None
) -> RotationPlan:
    """Produce a rotation plan (does not write anything). The caller sets these in
    ``.env``: the new key becomes primary, the current key becomes the grace-window
    previous key, and today's date is recorded."""
    settings = settings or get_settings()
    from nexo_os.clock import now

    when = today or now().date()
    new_key = generate_key()
    return RotationPlan(
        new_key=new_key,
        previous_key=settings.auth_cookie_key,
        rotated_on=when,
        env_lines={
            "NEXO_AUTH_COOKIE_KEY": new_key,
            "NEXO_AUTH_COOKIE_KEY_PREVIOUS": settings.auth_cookie_key,
            "NEXO_AUTH_COOKIE_KEY_ROTATED_ON": when.isoformat(),
        },
    )


# --- secret sourcing ----------------------------------------------------------


class SecretUnavailable(RuntimeError):
    """A configured secret backend cannot be reached. Fail closed - never fabricate."""


class SecretProvider(ABC):
    @abstractmethod
    def get(self, name: str) -> str | None:
        """Return the secret value for ``name`` or None if unset."""


class EnvSecretProvider(SecretProvider):
    """Reads from process environment (and, via pydantic-settings, the ``.env`` file)."""

    def get(self, name: str) -> str | None:
        import os

        return os.environ.get(name)


class _CloudSecretProvider(SecretProvider):
    """Base for cloud managers. Concrete subclasses import their client lazily and
    fail closed with an actionable message when it is missing or unconfigured."""

    label = "cloud"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get(self, name: str) -> str | None:  # pragma: no cover - requires cloud creds
        raise SecretUnavailable(
            f"Secret manager '{self.label}' selected but its client/configuration is not "
            f"available. Configure it or set NEXO_SECRET_MANAGER=env. Failing closed."
        )


class GcpSecretProvider(_CloudSecretProvider):
    label = "gcp"


class AwsSecretProvider(_CloudSecretProvider):
    label = "aws"


class VaultSecretProvider(_CloudSecretProvider):
    label = "vault"


_PROVIDERS = {
    SecretManager.env: EnvSecretProvider,
    SecretManager.gcp: GcpSecretProvider,
    SecretManager.aws: AwsSecretProvider,
    SecretManager.vault: VaultSecretProvider,
}


def get_secret_provider(settings: Settings | None = None) -> SecretProvider:
    settings = settings or get_settings()
    cls = _PROVIDERS[settings.secret_manager]
    if cls is EnvSecretProvider:
        return cls()
    return cls(settings)  # type: ignore[call-arg]
