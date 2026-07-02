"""SSO / federated identity (OIDC) - a code-real auth seam that fails closed.

``AuthProvider`` is the boundary the dashboard authenticates against. Two concrete
providers:

- ``PasswordAuthProvider`` - the existing bcrypt seat store (the default).
- ``OIDCAuthProvider`` - OpenID Connect. It builds the authorization-code-flow URL,
  and turns verified ID-token claims into a Nexo ``Identity`` whose role comes from the
  IAM group bindings (``enterprise.iam``).

Two deployment shapes are supported, both real:

1. **Proxy-verified** (``NEXO_OIDC_TRUST_PROXY_CLAIMS=true``): an upstream identity-aware
   proxy (Google IAP, oauth2-proxy, an API gateway) verifies the token and forwards the
   claims. Nexo maps claims -> role. This needs no crypto dependency.
2. **Locally verified**: Nexo verifies the ID token signature itself against the issuer
   JWKS. This uses PyJWT (the optional ``[sso]`` extra); without it, local verification
   fails closed rather than trusting an unverified token.

Selecting ``NEXO_AUTH_MODE=oidc`` without an issuer + client id raises - never a silent
fallback to open access.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from urllib.parse import urlencode

from nexo_os.config import AuthMode, Settings, get_settings
from nexo_os.enterprise import iam
from nexo_os.enterprise.observability import emit_security_event


class SSOConfigError(RuntimeError):
    """SSO is selected but not usable as configured. Fail closed."""


class SSOVerificationError(RuntimeError):
    """An ID token could not be verified. Fail closed - never admit the user."""


@dataclass(frozen=True)
class Identity:
    """An authenticated seat, whatever the provider. ``role`` is the resolved Nexo
    role; None means authenticated-but-unauthorized (deny-by-default)."""

    username: str
    name: str
    role: str | None
    email: str = ""
    source: str = "password"
    groups: list[str] = field(default_factory=list)


class AuthProvider(ABC):
    mode: AuthMode

    @abstractmethod
    def is_configured(self) -> bool: ...


class PasswordAuthProvider(AuthProvider):
    mode = AuthMode.password

    def is_configured(self) -> bool:
        return True

    def authenticate(self, username: str, password: str) -> Identity | None:
        from nexo_os.security import users as user_store

        users = user_store.load_users().get("usernames", {})
        info = users.get(username)
        if not info or not user_store.verify_password(password, info["password"]):
            emit_security_event("login_failed", actor=username, source="password")
            return None
        emit_security_event("login_ok", actor=username, source="password")
        return Identity(
            username=username,
            name=info.get("name", username),
            role=info.get("role"),
            email=info.get("email", ""),
            source="password",
        )


class OIDCAuthProvider(AuthProvider):
    mode = AuthMode.oidc

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def is_configured(self) -> bool:
        s = self.settings
        return bool(s.oidc_issuer and s.oidc_client_id)

    def _require_configured(self) -> None:
        if not self.is_configured():
            raise SSOConfigError(
                "NEXO_AUTH_MODE=oidc requires NEXO_OIDC_ISSUER and NEXO_OIDC_CLIENT_ID. "
                "Failing closed."
            )

    def build_authorization_url(self, authorization_endpoint: str, state: str, nonce: str) -> str:
        """Pure builder for the authorization-code-flow redirect. The endpoint comes
        from the issuer's discovery document (``discover``)."""
        self._require_configured()
        s = self.settings
        if not s.oidc_redirect_uri:
            raise SSOConfigError("NEXO_OIDC_REDIRECT_URI is required for the OIDC login flow.")
        query = urlencode(
            {
                "response_type": "code",
                "client_id": s.oidc_client_id,
                "redirect_uri": s.oidc_redirect_uri,
                "scope": s.oidc_scopes,
                "state": state,
                "nonce": nonce,
            }
        )
        sep = "&" if "?" in authorization_endpoint else "?"
        return f"{authorization_endpoint}{sep}{query}"

    def discover(self) -> dict:  # pragma: no cover - network
        """Fetch the OIDC discovery document (`.well-known/openid-configuration`)."""
        self._require_configured()
        import json
        import urllib.request

        url = self.settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
        with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))

    def verify_id_token(self, id_token: str) -> dict:  # pragma: no cover - needs IdP+PyJWT
        """Verify an ID token signature against the issuer JWKS and return its claims.
        Uses PyJWT (the ``[sso]`` extra). Without it, fails closed."""
        self._require_configured()
        try:
            import jwt
            from jwt import PyJWKClient
        except ImportError as exc:
            raise SSOConfigError(
                'Local OIDC verification needs PyJWT. Install with: pip install -e ".[sso]", '
                "or run behind a verifying proxy with NEXO_OIDC_TRUST_PROXY_CLAIMS=true."
            ) from exc
        conf = self.discover()
        signing_key = PyJWKClient(conf["jwks_uri"]).get_signing_key_from_jwt(id_token)
        try:
            return jwt.decode(
                id_token,
                signing_key.key,
                algorithms=conf.get("id_token_signing_alg_values_supported", ["RS256"]),
                audience=self.settings.oidc_client_id,
                issuer=self.settings.oidc_issuer,
            )
        except Exception as exc:  # jwt.InvalidTokenError and friends
            raise SSOVerificationError(f"ID token verification failed: {exc}") from exc

    def identity_from_claims(self, claims: dict) -> Identity:
        """Map verified OIDC claims to a Nexo ``Identity``. The role is resolved from
        the IdP groups via the IAM bindings; no matching binding -> role None (denied,
        unless a default role is configured)."""
        self._require_configured()
        sub = claims.get("sub")
        if not sub:
            raise SSOVerificationError("OIDC claims missing 'sub'.")
        email = claims.get("email", "")
        username = claims.get("preferred_username") or email or sub
        name = claims.get("name") or username
        groups = claims.get(self.settings.oidc_groups_claim, []) or []
        if isinstance(groups, str):
            groups = [g.strip() for g in groups.split(",") if g.strip()]
        resolution = iam.resolve_primary_role(list(groups), self.settings)
        emit_security_event(
            "login_ok" if resolution.role else "login_denied_no_role",
            actor=str(username),
            source="oidc",
            groups=len(groups),
        )
        return Identity(
            username=str(username),
            name=str(name),
            role=resolution.role,
            email=str(email),
            source="oidc",
            groups=list(groups),
        )

    def authenticate_claims(self, claims: dict) -> Identity:
        """Entry point when claims are already verified (proxy-verified deployment).
        Requires the trust flag so an unverified claims dict is never accepted silently."""
        if not self.settings.oidc_trust_proxy_claims:
            raise SSOConfigError(
                "Refusing to accept forwarded claims without NEXO_OIDC_TRUST_PROXY_CLAIMS=true. "
                "Either enable it (only behind a verifying proxy) or use verify_id_token."
            )
        return self.identity_from_claims(claims)


def get_auth_provider(settings: Settings | None = None) -> AuthProvider:
    """Factory: the auth provider for the configured mode. OIDC fails closed when not
    configured - never a silent fallback to password or open access."""
    settings = settings or get_settings()
    if settings.auth_mode == AuthMode.oidc:
        provider = OIDCAuthProvider(settings)
        if not provider.is_configured():
            raise SSOConfigError(
                "NEXO_AUTH_MODE=oidc but OIDC is not configured (issuer/client id). Failing closed."
            )
        return provider
    return PasswordAuthProvider()
