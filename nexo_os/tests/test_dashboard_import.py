"""Phase 7: the dashboard module imports cleanly and exposes a main() entry, without
launching Streamlit."""

from __future__ import annotations


def test_dashboard_imports_and_has_main() -> None:
    from nexo_os.dashboard import app

    assert callable(app.main)
