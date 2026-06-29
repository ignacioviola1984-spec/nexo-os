"""Demo deployment wiring: demo_mode reads from env, and the self-bootstrap entry is
importable. (The full seed+bootstrap path is exercised manually; it is slow.)"""

from __future__ import annotations

from nexo_os.config import get_settings


def test_demo_mode_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("NEXO_DEMO_MODE", "1")
    get_settings.cache_clear()
    try:
        assert get_settings().demo_mode is True
    finally:
        get_settings.cache_clear()


def test_demo_mode_defaults_false() -> None:
    get_settings.cache_clear()
    try:
        assert get_settings().demo_mode is False
    finally:
        get_settings.cache_clear()


def test_bootstrap_entry_importable() -> None:
    from nexo_os.dashboard import bootstrap

    assert callable(bootstrap.ensure_demo_ready)
