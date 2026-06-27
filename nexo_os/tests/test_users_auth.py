"""Phase 7: user store, bcrypt hashing, RBAC roles, and the first-boot bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexo_os.config import get_settings
from nexo_os.security import users as u


@pytest.fixture
def users_env(tmp_path: Path, monkeypatch):
    path = tmp_path / "users.json"
    monkeypatch.setenv("NEXO_USERS_PATH", str(path))
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


def test_hash_and_verify_roundtrip() -> None:
    h = u.hash_password("s3cret")
    assert h != "s3cret"
    assert u.verify_password("s3cret", h)
    assert not u.verify_password("wrong", h)


def test_add_user_and_role(users_env) -> None:
    u.add_user("op1", "Operadora", "pw", u.ROLE_OPERADOR)
    assert u.get_role("op1") == u.ROLE_OPERADOR
    creds = u.to_authenticator_credentials()
    assert creds["usernames"]["op1"]["roles"] == [u.ROLE_OPERADOR]
    assert "password" in creds["usernames"]["op1"]


def test_add_user_rejects_bad_role(users_env) -> None:
    with pytest.raises(ValueError, match="Rol inválido"):
        u.add_user("x", "X", "pw", "superuser")


def test_bootstrap_fails_closed_without_password(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEXO_USERS_PATH", str(tmp_path / "users.json"))
    monkeypatch.setenv("NEXO_ADMIN_PASSWORD", "")
    get_settings.cache_clear()
    try:
        assert u.bootstrap_admin() == 1
        assert u.load_users()["usernames"] == {}
    finally:
        get_settings.cache_clear()


def test_bootstrap_creates_admin_idempotently(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEXO_USERS_PATH", str(tmp_path / "users.json"))
    monkeypatch.setenv("NEXO_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("NEXO_ADMIN_PASSWORD", "secret123")
    get_settings.cache_clear()
    try:
        assert u.bootstrap_admin() == 0
        assert u.get_role("admin") == u.ROLE_ADMIN
        # second call is a no-op, not a duplicate
        assert u.bootstrap_admin() == 0
        assert len(u.load_users()["usernames"]) == 1
    finally:
        get_settings.cache_clear()
