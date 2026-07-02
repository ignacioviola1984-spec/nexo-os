"""Central configuration (pydantic-settings). No magic numbers in agent/core code:
every tunable threshold lives here and is documented.

Settings are sourced from environment variables and an optional `.env` file. The
build runs end-to-end on synthetic data with only ANTHROPIC_API_KEY and the
bootstrap admin set; all BigQuery settings are optional and unused unless
NEXO_DATA_SOURCE=bigquery.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent


class DataSource(StrEnum):
    """Which repository backend serves domain data."""

    synthetic = "synthetic"
    bigquery = "bigquery"
    gcs = "gcs"  # cloud object storage (Google Cloud Storage), domain extracts as Parquet
    turso = "turso"  # hosted libSQL (SQLite-compatible)


class SystemStore(StrEnum):
    """Where the system tables (acciones, agent_runs, audit_log) live. `default`
    keeps them with the domain backend; `turso` routes them to hosted Turso even
    when the domain source is synthetic or bigquery (the hybrid mode)."""

    default = "default"
    turso = "turso"


class Environment(StrEnum):
    """Deployment environment. `production` tightens the enterprise controls:
    weak secrets, open demo access and unpinned config fail the security review."""

    dev = "dev"
    staging = "staging"
    production = "production"


class AuthMode(StrEnum):
    """How seats authenticate. `password` is the built-in bcrypt store; `oidc` is
    the SSO seam (enterprise/sso.py) - federated identity via an external IdP,
    fails closed without issuer/client configured."""

    password = "password"
    oidc = "oidc"


class SecretManager(StrEnum):
    """Where runtime secrets are sourced. `env` reads process env / `.env`;
    `gcp` / `aws` / `vault` are cloud secret-manager seams (enterprise/secrets.py),
    each fails closed when selected without its client configured."""

    env = "env"
    gcp = "gcp"
    aws = "aws"
    vault = "vault"


class MoraBuckets(BaseModel):
    """Aging bucket edges (days) for overdue installments. Computed at read-time
    relative to the run snapshot date, never stored."""

    b1_30: int = 30
    b31_60: int = 60
    b61_90: int = 90
    # anything strictly greater than b61_90 falls in the 90+ bucket


class Thresholds(BaseModel):
    """All agent thresholds. Documented and tunable; agent code reads these only."""

    # --- aging / collections ---
    mora: MoraBuckets = Field(default_factory=MoraBuckets)
    # An installment is "vencida" once days past due > 0 relative to the snapshot.

    # --- renewals: expiry windows (days from snapshot) ---
    expiry_windows_days: tuple[int, int, int] = (30, 60, 90)

    # --- lead/quote SLA (days of no movement before a breach) ---
    lead_sla_days: int = 5  # a lead with no movement past this is breached
    lead_no_quote_days: int = 7  # a lead with no quote within this window
    quote_not_presented_days: int = 10  # quote emitida but never presentada

    # --- conversion floors (below => coaching/review flag), as fractions 0..1 ---
    conversion_floor_lead_to_win: float = 0.15
    conversion_floor_quote_to_bind: float = 0.30

    # --- pipeline: deterministic win-probability by stage (weighted forecast) ---
    stage_probabilities: dict[str, float] = Field(
        default_factory=lambda: {
            "nuevo": 0.05,
            "contactado": 0.15,
            "cotizado": 0.35,
            "presentado": 0.60,
            "ganado": 1.0,
            "perdido": 0.0,
        }
    )
    pipeline_aging_days: int = 14  # opportunity aging in a single stage past this

    # --- concentration review (cartera) ---
    hhi_concentration_alert: float = 0.25  # HHI above this => over-concentration flag

    # --- profitability ---
    loss_ratio_alert: float = 0.70  # ramo loss ratio above this => unprofitable review

    # --- retention: long-inactivity churn signal (days since last interaction) ---
    inactivity_days: int = 180

    # --- commission tracking: aging of receivable (days since period close) ---
    commission_overdue_days: int = 45

    # --- priority cutoffs by amount at stake (ARS). Items with no natural amount
    #     (SLA breaches, data-quality flags) route by urgency only. ---
    priority_alta_ars: float = 500_000.0
    priority_media_ars: float = 100_000.0
    # urgency-only branch: days-of-urgency cutoffs when monto_en_juego_ars is None
    priority_alta_urgency_days: int = 90
    priority_media_urgency_days: int = 30

    # --- reconciliation tolerance (ARS) between agents in the reliability layer ---
    reconciliation_tolerance_ars: float = 1.0


class Settings(BaseSettings):
    """Process-wide settings. Immutable after load."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- data source ---
    data_source: DataSource = Field(default=DataSource.synthetic, alias="NEXO_DATA_SOURCE")

    # --- model (narration only) ---
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    model: str = Field(default="claude-sonnet-4-6", alias="NEXO_MODEL")
    model_max_tokens: int = Field(default=700, alias="NEXO_MODEL_MAX_TOKENS")
    # cap on model-narrated actions per run (rest get deterministic grounded facts)
    narrate_model_cap: int = Field(default=40, alias="NEXO_NARRATE_MODEL_CAP")

    # --- snapshot date override (else the synthetic dataset's documented date) ---
    snapshot_fecha_override: date | None = Field(default=None, alias="NEXO_SNAPSHOT_FECHA")

    # --- synthetic dataset ---
    synthetic_seed: int = Field(default=20260630, alias="NEXO_SYNTHETIC_SEED")
    synthetic_snapshot_fecha: date = Field(
        default=date(2026, 6, 30), alias="NEXO_SYNTHETIC_SNAPSHOT_FECHA"
    )

    # --- local stores ---
    synthetic_db_path: Path = Field(
        default=PACKAGE_ROOT / "data" / "synthetic" / "nexo.duckdb",
        alias="NEXO_SYNTHETIC_DB_PATH",
    )
    runtime_db_path: Path = Field(
        default=PACKAGE_ROOT / "data" / "runtime" / "nexo.duckdb",
        alias="NEXO_RUNTIME_DB_PATH",
    )
    users_path: Path = Field(default=REPO_ROOT / "config" / "users.json", alias="NEXO_USERS_PATH")

    # --- auth ---
    auth_cookie_key: str = Field(default="change-me", alias="NEXO_AUTH_COOKIE_KEY")
    auth_cookie_name: str = Field(default="nexo_auth", alias="NEXO_AUTH_COOKIE_NAME")
    auth_session_minutes: int = Field(default=480, alias="NEXO_AUTH_SESSION_MINUTES")

    # --- bootstrap admin (first boot only) ---
    admin_username: str = Field(default="admin", alias="NEXO_ADMIN_USERNAME")
    admin_password: str | None = Field(default=None, alias="NEXO_ADMIN_PASSWORD")
    admin_name: str = Field(default="Administrador", alias="NEXO_ADMIN_NAME")

    # --- public demo (Streamlit Cloud): auto-seed + auto-bootstrap + show creds ---
    demo_mode: bool = Field(default=False, alias="NEXO_DEMO_MODE")

    # --- BigQuery backend (optional; default source is synthetic) ---
    bq_project: str | None = Field(default=None, alias="NEXO_BQ_PROJECT")
    bq_dataset: str = Field(default="nexo", alias="NEXO_BQ_DATASET")
    bq_credentials_path: Path | None = Field(default=None, alias="NEXO_BQ_CREDENTIALS_PATH")

    # --- Google Cloud Storage backend (optional; domain extracts as Parquet) ---
    gcs_bucket: str | None = Field(default=None, alias="NEXO_GCS_BUCKET")
    gcs_prefix: str = Field(default="nexo/", alias="NEXO_GCS_PREFIX")
    gcs_credentials_path: Path | None = Field(default=None, alias="NEXO_GCS_CREDENTIALS_PATH")

    # --- Turso / libSQL backend (optional; opt-in, fails closed) ---
    # url is `libsql://<db>.turso.io` (remote) or `file:./nexo_turso.db` (local dev/test);
    # auth token is required for remote, unused for a local file.
    turso_database_url: str | None = Field(default=None, alias="NEXO_TURSO_DATABASE_URL")
    turso_auth_token: str | None = Field(default=None, alias="NEXO_TURSO_AUTH_TOKEN")
    # Hybrid override: keep domain on synthetic/bigquery but persist the system tables
    # in Turso (survives Streamlit Cloud's ephemeral filesystem across restarts).
    system_store: SystemStore = Field(default=SystemStore.default, alias="NEXO_SYSTEM_STORE")

    # --- multi-tenancy: per-tenant data isolation ---
    # One deployment serves one tenant, selected by NEXO_TENANT_ID. Each tenant's
    # data lives in its own store / dataset / GCS prefix (hard isolation). "default"
    # keeps the original paths (single-tenant behavior, backward compatible).
    tenant_id: str = Field(default="default", alias="NEXO_TENANT_ID")

    # ==================== enterprise / production hardening ====================
    # Every seam below is code-real and fails closed: selecting it without its
    # configuration raises rather than degrading silently. `production` tightens
    # the security review and SOC2 control checks.

    # --- environment + release identity (observability, controls, rollback) ---
    environment: Environment = Field(default=Environment.dev, alias="NEXO_ENV")
    service_version: str = Field(default="2.0.0", alias="NEXO_SERVICE_VERSION")
    git_sha: str | None = Field(default=None, alias="NEXO_GIT_SHA")

    # --- SSO / federated identity (enterprise/sso.py) ---
    auth_mode: AuthMode = Field(default=AuthMode.password, alias="NEXO_AUTH_MODE")
    oidc_issuer: str | None = Field(default=None, alias="NEXO_OIDC_ISSUER")
    oidc_client_id: str | None = Field(default=None, alias="NEXO_OIDC_CLIENT_ID")
    oidc_client_secret: str | None = Field(default=None, alias="NEXO_OIDC_CLIENT_SECRET")
    oidc_redirect_uri: str | None = Field(default=None, alias="NEXO_OIDC_REDIRECT_URI")
    oidc_scopes: str = Field(default="openid email profile groups", alias="NEXO_OIDC_SCOPES")
    # Claim that carries the IdP group memberships used for IAM role binding.
    oidc_groups_claim: str = Field(default="groups", alias="NEXO_OIDC_GROUPS_CLAIM")
    # When true, trust that an upstream proxy (IAP / oauth2-proxy) already verified
    # the ID token signature and forwards claims. When false, a local verifier
    # (PyJWT, optional extra) must validate the signature or auth fails closed.
    oidc_trust_proxy_claims: bool = Field(default=False, alias="NEXO_OIDC_TRUST_PROXY_CLAIMS")

    # --- cloud IAM: external group -> Nexo role bindings (enterprise/iam.py) ---
    # JSON mapping {"<idp-group>": "<nexo-role>"}, or a path to such a JSON file.
    iam_role_bindings: str | None = Field(default=None, alias="NEXO_IAM_ROLE_BINDINGS")
    iam_bindings_path: Path | None = Field(default=None, alias="NEXO_IAM_BINDINGS_PATH")
    # Role assigned to a federated user matched by no binding (deny-by-default: none).
    iam_default_role: str | None = Field(default=None, alias="NEXO_IAM_DEFAULT_ROLE")

    # --- secrets management + rotation (enterprise/secrets.py) ---
    secret_manager: SecretManager = Field(default=SecretManager.env, alias="NEXO_SECRET_MANAGER")
    # Previous cookie key kept valid during a rotation grace window so live sessions
    # are not force-logged-out the moment the primary key rotates.
    auth_cookie_key_previous: str | None = Field(
        default=None, alias="NEXO_AUTH_COOKIE_KEY_PREVIOUS"
    )
    # ISO date the primary cookie key was last rotated; the security review warns
    # when it exceeds the max age in production.
    auth_cookie_key_rotated_on: date | None = Field(
        default=None, alias="NEXO_AUTH_COOKIE_KEY_ROTATED_ON"
    )
    secret_max_age_days: int = Field(default=90, alias="NEXO_SECRET_MAX_AGE_DAYS")

    # --- observability / monitoring (enterprise/observability.py) ---
    metrics_enabled: bool = Field(default=True, alias="NEXO_METRICS_ENABLED")
    # Freshness SLA (hours) for the domain snapshot; monitoring alerts past it.
    data_freshness_sla_hours: int = Field(default=48, alias="NEXO_DATA_FRESHNESS_SLA_HOURS")

    # --- thresholds ---
    thresholds: Thresholds = Field(default_factory=Thresholds)

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.production

    @property
    def snapshot_fecha(self) -> date:
        """The effective 'as of' date for a run."""
        return self.snapshot_fecha_override or self.synthetic_snapshot_fecha


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor used across the codebase."""
    return Settings()
