"""Phase 0 smoke tests: the package imports, config loads with safe defaults, and
the i18n money formatter is deterministic."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from nexo_os import __version__
from nexo_os.config import DataSource, get_settings
from nexo_os.i18n import SIN_DATOS, fmt_ars, fmt_pct


def test_version() -> None:
    assert __version__ == "2.0.0"


def test_settings_defaults_to_synthetic() -> None:
    s = get_settings()
    assert s.data_source is DataSource.synthetic
    assert isinstance(s.snapshot_fecha, date)
    # thresholds present and sane
    assert s.thresholds.expiry_windows_days == (30, 60, 90)
    assert s.thresholds.stage_probabilities["ganado"] == 1.0


def test_fmt_ars_argentine_convention() -> None:
    assert fmt_ars(Decimal("1234567.5")) == "$ 1.234.567,50"
    assert fmt_ars(0) == "$ 0,00"
    assert fmt_ars(Decimal("-2500")) == "-$ 2.500,00"


def test_fmt_ars_sin_datos_when_none() -> None:
    assert fmt_ars(None) == SIN_DATOS


def test_fmt_pct() -> None:
    assert fmt_pct(0.153) == "15,3%"
    assert fmt_pct(None) == SIN_DATOS
