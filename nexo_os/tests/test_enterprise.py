"""Tests for the enterprise / production-hardening layer: RBAC, SSO/OIDC, cloud IAM,
observability, data contracts, secrets + rotation, SOC2-style controls, security review,
release/rollback, and incident response.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from nexo_os.config import AuthMode, Environment, Settings


def mk(**over) -> Settings:
    """A Settings object with explicit overrides (bypasses .env for determinism)."""
    return Settings().model_copy(update=over)


# ------------------------------------------------------------------ RBAC --------


def test_rbac_deny_by_default_and_least_privilege():
    from nexo_os.enterprise import rbac

    assert rbac.permissions_for(None) == frozenset()
    assert rbac.permissions_for("nonsense") == frozenset()
    # admin holds everything; viewer is a strict subset of operador
    assert rbac.permissions_for(rbac.ROLE_ADMIN) == frozenset(rbac.Permission)
    assert rbac.permissions_for(rbac.ROLE_VIEWER) < rbac.permissions_for(rbac.ROLE_OPERADOR)
    # only admin manages users
    assert rbac.has_permission(rbac.ROLE_ADMIN, rbac.Permission.MANAGE_USERS)
    assert not rbac.has_permission(rbac.ROLE_OPERADOR, rbac.Permission.MANAGE_USERS)


def test_rbac_require_raises():
    from nexo_os.enterprise import rbac

    rbac.require(rbac.ROLE_OPERADOR, rbac.Permission.INBOX_RESOLVE)  # no raise
    with pytest.raises(rbac.PermissionDenied):
        rbac.require(rbac.ROLE_VIEWER, rbac.Permission.INBOX_RESOLVE)
    with pytest.raises(rbac.PermissionDenied):
        rbac.require(rbac.ROLE_AUDITOR, rbac.Permission.INBOX_RESOLVE)


def test_review_enforces_rbac_before_lookup(repo):
    from nexo_os.audit import AuditWriter
    from nexo_os.data.models import AccionEstado
    from nexo_os.enterprise.rbac import ROLE_OPERADOR, ROLE_VIEWER, PermissionDenied
    from nexo_os.review import ReviewError, resolve_accion

    audit = AuditWriter(repo)
    # viewer is refused at the maker-checker boundary regardless of the action
    with pytest.raises(PermissionDenied):
        resolve_accion(repo, audit, "missing", AccionEstado.aprobada, "u", revisor_role=ROLE_VIEWER)
    # operador passes RBAC and then fails closed on the unknown action (ReviewError)
    with pytest.raises(ReviewError):
        resolve_accion(
            repo, audit, "missing", AccionEstado.aprobada, "u", revisor_role=ROLE_OPERADOR
        )
    # None keeps the internal call backward-compatible (no RBAC, still fails on lookup)
    with pytest.raises(ReviewError):
        resolve_accion(repo, audit, "missing", AccionEstado.aprobada, "u")


# ------------------------------------------------------------------- IAM --------


def test_iam_bindings_precedence_and_deny():
    from nexo_os.enterprise import iam

    s = mk(iam_role_bindings='{"g-admin":"admin","g-ops":"operador","g-audit":"auditor"}')
    # most-privileged wins when several match
    res = iam.resolve_primary_role(["g-ops", "g-admin"], s)
    assert res.role == "admin" and not res.via_default
    # no match, no default -> denied
    assert iam.resolve_primary_role(["nope"], s).role is None
    assert iam.resolve_roles(["g-ops", "g-audit"], s) == ["operador", "auditor"]


def test_iam_default_role_and_validation():
    from nexo_os.enterprise import iam

    s = mk(iam_role_bindings="{}", iam_default_role="viewer")
    res = iam.resolve_primary_role(["anything"], s)
    assert res.role == "viewer" and res.via_default
    # bad role in bindings -> config error
    with pytest.raises(iam.IAMConfigError):
        iam.load_bindings(mk(iam_role_bindings='{"g":"superuser"}'))
    # no bindings, no default -> flagged problem
    assert iam.validate_bindings(mk(iam_role_bindings="{}"))


def test_iam_bindings_from_file(tmp_path):
    from nexo_os.enterprise import iam

    p = tmp_path / "b.json"
    p.write_text('{"grp":"operador"}', encoding="utf-8")
    assert iam.load_bindings(mk(iam_bindings_path=p)) == {"grp": "operador"}


# ------------------------------------------------------------------- SSO --------


def _oidc_settings(**over) -> Settings:
    base = dict(
        auth_mode=AuthMode.oidc,
        oidc_issuer="https://idp.example.com",
        oidc_client_id="client-123",
        oidc_redirect_uri="https://nexo.example.com/cb",
        iam_role_bindings='{"g-admin":"admin","g-ops":"operador"}',
    )
    base.update(over)
    return mk(**base)


def test_sso_provider_selection_and_fail_closed():
    from nexo_os.enterprise.sso import (
        OIDCAuthProvider,
        PasswordAuthProvider,
        SSOConfigError,
        get_auth_provider,
    )

    assert isinstance(get_auth_provider(mk(auth_mode=AuthMode.password)), PasswordAuthProvider)
    assert isinstance(get_auth_provider(_oidc_settings()), OIDCAuthProvider)
    # oidc selected but unconfigured -> fail closed
    with pytest.raises(SSOConfigError):
        get_auth_provider(mk(auth_mode=AuthMode.oidc))


def test_sso_identity_from_claims_maps_role():
    from nexo_os.enterprise.sso import OIDCAuthProvider, SSOVerificationError

    p = OIDCAuthProvider(_oidc_settings())
    ident = p.identity_from_claims(
        {"sub": "u1", "email": "a@b.com", "name": "A", "groups": ["g-admin"]}
    )
    assert ident.role == "admin" and ident.source == "oidc" and ident.username == "a@b.com"
    # authenticated but unmapped -> role None (deny-by-default)
    assert p.identity_from_claims({"sub": "u2", "groups": ["none"]}).role is None
    # missing sub -> fail closed
    with pytest.raises(SSOVerificationError):
        p.identity_from_claims({"email": "x@y.com"})


def test_sso_authorization_url_and_proxy_claims():
    from nexo_os.enterprise.sso import OIDCAuthProvider, SSOConfigError

    p = OIDCAuthProvider(_oidc_settings())
    url = p.build_authorization_url("https://idp.example.com/authorize", "state1", "nonce1")
    assert "client_id=client-123" in url and "state=state1" in url and "response_type=code" in url
    # forwarded claims refused unless the trust flag is set
    with pytest.raises(SSOConfigError):
        p.authenticate_claims({"sub": "u", "groups": ["g-ops"]})
    p2 = OIDCAuthProvider(_oidc_settings(oidc_trust_proxy_claims=True))
    assert p2.authenticate_claims({"sub": "u", "groups": ["g-ops"]}).role == "operador"


# --------------------------------------------------------- observability --------


def test_metrics_registry_and_prometheus():
    from nexo_os.enterprise.observability import MetricsRegistry

    m = MetricsRegistry()
    m.describe("nexo_test_total", "a test counter")
    m.inc("nexo_test_total", event="x")
    m.inc("nexo_test_total", event="x")
    m.set_gauge("nexo_test_gauge", 3.0)
    assert m.get_counter("nexo_test_total", event="x") == 2.0
    text = m.render_prometheus()
    assert "# TYPE nexo_test_total counter" in text
    assert 'nexo_test_total{event="x"} 2' in text
    with pytest.raises(ValueError):
        m.inc("nexo_test_total", value=-1)


def test_readiness_config_only_and_weak_secret_in_prod():
    from nexo_os.enterprise.observability import readiness

    ok = readiness(settings=mk(auth_cookie_key="x" * 40))
    assert ok.ready and any(c.name == "secret_hygiene" for c in ok.checks)
    prod_weak = readiness(
        settings=mk(environment=Environment.production, auth_cookie_key="change-me")
    )
    assert not prod_weak.ready  # critical secret_hygiene failure blocks readiness


# ------------------------------------------------------- data contracts ---------


def _good_clientes_df() -> pd.DataFrame:
    from nexo_os.enterprise.data_contracts import domain_contracts

    contract = next(c for c in domain_contracts() if c.table == "clientes")
    return pd.DataFrame({col: ["v", "w"] for col in contract.required_columns}).assign(
        cliente_id=["C1", "C2"]
    )


def test_data_contracts_structural_pass_and_violations():
    from nexo_os.enterprise.data_contracts import domain_contracts, evaluate_dataframe

    contracts = {c.table: c for c in domain_contracts()}
    assert len(contracts) == 10
    contract = contracts["clientes"]
    good = _good_clientes_df()
    assert evaluate_dataframe(contract, good).ok

    # missing column
    r = evaluate_dataframe(contract, good.drop(columns=["nombre"]))
    assert not r.ok and any("missing" in v for v in r.violations)
    # duplicate primary key
    dup = pd.concat([good, good.iloc[[0]]])
    r = evaluate_dataframe(contract, dup)
    assert not r.ok and any("duplicate" in v for v in r.violations)
    # too few rows
    assert not evaluate_dataframe(contract, good.iloc[0:0]).ok


def test_data_contract_freshness_opt_in():
    from datetime import datetime

    from nexo_os.enterprise.data_contracts import (
        domain_contracts,
        evaluate_dataframe,
        with_freshness,
    )

    base = next(c for c in domain_contracts() if c.table == "interacciones")
    assert base.freshness_column is None  # off by default (no false stale failures)
    fresh = with_freshness(base, "fecha", 48) if "fecha" in base.required_columns else None
    # pick a real date-ish column present in the contract
    col = next(c for c in base.required_columns if "fecha" in c)
    fresh = with_freshness(base, col, 48)
    df = pd.DataFrame({c: ["x"] for c in base.required_columns})
    df[col] = [date(2000, 1, 1)]
    df["interaccion_id"] = ["I1"]
    r = evaluate_dataframe(fresh, df, as_of=datetime(2026, 6, 30))
    assert not r.ok and any("stale" in v for v in r.violations)


def test_validate_source_reader_error_is_violation():
    from nexo_os.enterprise.data_contracts import domain_contracts, validate_source

    def reader(table):
        raise RuntimeError("boom")

    results = validate_source(reader, contracts=domain_contracts()[:2])
    assert all(not r.ok and any("unreadable" in v for v in r.violations) for r in results)


# ------------------------------------------------------------- secrets ----------


def test_cookie_key_weakness_and_generation():
    from nexo_os.enterprise.secrets import cookie_key_is_weak, generate_key

    assert (
        cookie_key_is_weak("") and cookie_key_is_weak("change-me") and cookie_key_is_weak("short")
    )
    assert not cookie_key_is_weak("x" * 40)
    k = generate_key()
    assert len(k) >= 32 and not cookie_key_is_weak(k)


def test_active_cookie_keys_and_rotation_grace():
    from nexo_os.enterprise.secrets import active_cookie_keys

    s = mk(auth_cookie_key="new" + "x" * 30, auth_cookie_key_previous="old" + "y" * 30)
    keys = active_cookie_keys(s)
    assert keys[0].startswith("new") and any(k.startswith("old") for k in keys)


def test_rotation_due_and_plan():
    from nexo_os.enterprise.secrets import plan_cookie_key_rotation, rotation_due, secret_age_days

    # unknown rotation date: due in production, not in dev
    assert rotation_due(mk(environment=Environment.production)) is True
    assert rotation_due(mk(environment=Environment.dev)) is False
    old = mk(auth_cookie_key_rotated_on=date(2000, 1, 1), secret_max_age_days=90)
    assert secret_age_days(old, today=date(2026, 1, 1)) > 90 and rotation_due(
        old, today=date(2026, 1, 1)
    )
    plan = plan_cookie_key_rotation(mk(auth_cookie_key="old" + "z" * 30), today=date(2026, 7, 2))
    from nexo_os.enterprise.secrets import cookie_key_is_weak

    assert not cookie_key_is_weak(plan.new_key)
    assert plan.env_lines["NEXO_AUTH_COOKIE_KEY_PREVIOUS"].startswith("old")


def test_cloud_secret_provider_fails_closed():
    from nexo_os.config import SecretManager
    from nexo_os.enterprise.secrets import SecretUnavailable, get_secret_provider

    prov = get_secret_provider(mk(secret_manager=SecretManager.gcp))
    with pytest.raises(SecretUnavailable):
        prov.get("ANYTHING")


# ------------------------------------------------------------- controls ---------


def test_controls_all_pass_in_dev():
    from nexo_os.enterprise.controls import ControlStatus, run_controls

    results = run_controls(mk(auth_cookie_key="x" * 40))
    fails = [r for r in results if r.status == ControlStatus.FAIL]
    assert not fails, f"unexpected control failures: {[(r.id, r.evidence) for r in fails]}"


def test_controls_flag_open_access_in_prod():
    from nexo_os.enterprise.controls import ControlStatus, c_access_control

    r = c_access_control(mk(environment=Environment.production, demo_mode=True))
    assert r.status == ControlStatus.FAIL


# -------------------------------------------------------- security review -------


def test_security_review_clean_passes_gate():
    from nexo_os.enterprise.security_review import gate, run_security_review

    findings = run_security_review(
        mk(auth_cookie_key="x" * 40, auth_cookie_key_rotated_on=date(2026, 7, 1))
    )
    assert gate(findings)


def test_security_review_prod_weak_key_is_critical():
    from nexo_os.enterprise.security_review import Severity, gate, run_security_review

    findings = run_security_review(
        mk(environment=Environment.production, auth_cookie_key="change-me")
    )
    assert not gate(findings)
    assert any(f.id == "SEC-001" and f.severity == Severity.CRITICAL for f in findings)


# --------------------------------------------------------- release/rollback -----


def test_schema_fingerprint_stable():
    from nexo_os.enterprise.release import schema_fingerprint

    fp = schema_fingerprint()
    assert len(fp) == 12 and fp == schema_fingerprint()


def test_rollback_safe_and_blocked(tmp_path):
    from dataclasses import replace

    from nexo_os.enterprise.release import (
        current_manifest,
        load_manifest,
        plan_rollback,
        write_manifest,
    )

    cur = current_manifest(mk())
    assert plan_rollback(cur, cur).ok  # same release is safe
    # schema change since the target release -> blocked
    stale = replace(cur, schema_fingerprint="deadbeef0000", version="1.9.0")
    plan = plan_rollback(stale, cur)
    assert not plan.ok and any("schema" in r for r in plan.reasons)
    # write/load roundtrip
    p = tmp_path / "rel.json"
    write_manifest(p, mk())
    assert load_manifest(p).schema_fingerprint == cur.schema_fingerprint


# --------------------------------------------------------------- incident -------


def test_incident_snapshot_and_audit_record(repo):
    from nexo_os.enterprise.incident import Severity, open_incident, render_incident
    from nexo_os.orchestrator import run_cycle

    run_cycle(repo=repo)  # populate audit + runs
    before = len(repo.get_audit_events())
    inc = open_incident(repo, summary="test", severity=Severity.SEV1, opened_by="nacho")
    assert inc.snapshot.audit_chain_ok
    assert inc.snapshot.runs_total >= 1
    assert len(repo.get_audit_events()) == before + 1  # incident recorded immutably
    text = render_incident(inc)
    assert inc.id in text and "SEV1" in text
