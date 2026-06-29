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

    # --- thresholds ---
    thresholds: Thresholds = Field(default_factory=Thresholds)

    @property
    def snapshot_fecha(self) -> date:
        """The effective 'as of' date for a run."""
        return self.snapshot_fecha_override or self.synthetic_snapshot_fecha


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor used across the codebase."""
    return Settings()
