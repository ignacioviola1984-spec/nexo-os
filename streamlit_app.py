"""Streamlit Community Cloud entry point.

Deploy: point Streamlit Cloud at this repo with main file `streamlit_app.py`. It works
with zero secrets — synthetic data + a demo admin are bootstrapped on first start, and
narration falls back to deterministic grounded text when no ANTHROPIC_API_KEY is set.

Optional Streamlit secrets (Settings -> Secrets) override the demo defaults:
    ANTHROPIC_API_KEY = "sk-ant-..."     # enables model-written Spanish prose
    NEXO_ADMIN_USERNAME = "demo"
    NEXO_ADMIN_PASSWORD = "your-demo-password"
    NEXO_AUTH_COOKIE_KEY = "a-random-string"
"""

from __future__ import annotations

import os

import streamlit as st

# 1) map any provided Streamlit secrets into the environment (pydantic-settings reads env)
_SECRET_KEYS = [
    "ANTHROPIC_API_KEY",
    "NEXO_MODEL",
    "NEXO_DATA_SOURCE",
    "NEXO_ADMIN_USERNAME",
    "NEXO_ADMIN_PASSWORD",
    "NEXO_ADMIN_NAME",
    "NEXO_AUTH_COOKIE_KEY",
]
try:
    for _k in _SECRET_KEYS:
        if _k in st.secrets and _k not in os.environ:
            os.environ[_k] = str(st.secrets[_k])
except Exception:  # no secrets.toml present -> use demo defaults below
    pass

# 2) zero-config demo defaults (a public demo over synthetic data)
os.environ.setdefault("NEXO_DEMO_MODE", "1")
os.environ.setdefault("NEXO_ADMIN_USERNAME", "demo")
os.environ.setdefault("NEXO_ADMIN_PASSWORD", "nexo-demo-2026")
os.environ.setdefault("NEXO_ADMIN_NAME", "Demo")
os.environ.setdefault("NEXO_AUTH_COOKIE_KEY", "nexo-demo-cookie-key-change-me")

# 3) load settings AFTER the environment is set, then bootstrap data + login
from nexo_os.config import get_settings  # noqa: E402

get_settings.cache_clear()

from nexo_os.dashboard.bootstrap import ensure_demo_ready  # noqa: E402


@st.cache_resource
def _bootstrap_once() -> bool:
    ensure_demo_ready()
    return True


_bootstrap_once()

from nexo_os.dashboard.app import main  # noqa: E402

main()
