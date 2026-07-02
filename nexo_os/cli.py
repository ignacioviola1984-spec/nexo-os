"""Cross-platform task runner / entry point: `python -m nexo_os <command>`
(or the `nexo` console script). This is the portable equivalent of the Makefile
targets - `make` is not assumed to be installed.

Commands are wired lazily so that early-phase commands work before later-phase
modules exist.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from nexo_os.config import get_settings
from nexo_os.logging_setup import configure_logging, get_logger

REPO_ROOT = Path(__file__).resolve().parent.parent


def _cmd_seed(args: argparse.Namespace) -> int:
    from nexo_os.data.generate import generate_and_load

    generate_and_load()
    return 0


def _cmd_bootstrap_admin(args: argparse.Namespace) -> int:
    from nexo_os.security.users import bootstrap_admin

    return bootstrap_admin()


def _cmd_run(args: argparse.Namespace) -> int:
    """Launch the Streamlit dashboard."""
    app = REPO_ROOT / "nexo_os" / "dashboard" / "app.py"
    if not app.exists():
        print(f"Dashboard not built yet (missing {app}).", file=sys.stderr)
        return 1
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app)])


def _cmd_orchestrate(args: argparse.Namespace) -> int:
    """Run one full orchestrator cycle headless (no dashboard)."""
    from nexo_os.orchestrator import run_cycle

    ctx = run_cycle()
    print(ctx.summary_line())
    return 0


def _cmd_test(args: argparse.Namespace) -> int:
    return subprocess.call([sys.executable, "-m", "pytest", *args.extra])


def _cmd_eval(args: argparse.Namespace) -> int:
    from nexo_os.evals.runner import main as eval_main

    return eval_main()


def _cmd_lint(args: argparse.Namespace) -> int:
    rc = subprocess.call([sys.executable, "-m", "ruff", "check", "nexo_os"])
    rc |= subprocess.call([sys.executable, "-m", "black", "--check", "nexo_os"])
    return rc


def _cmd_bq_validate(args: argparse.Namespace) -> int:
    """Validate a live BigQuery dataset against the canonical DDL."""
    from nexo_os.data.bq_validate import validate

    return validate()


def _cmd_turso_seed(args: argparse.Namespace) -> int:
    """Load the synthetic dataset into the configured Turso/libSQL database."""
    from nexo_os.data.turso_seed import seed_turso

    counts = seed_turso()
    print("Seeded Turso:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


# ------------------------------------------------------------- enterprise ------


def _cmd_healthcheck(args: argparse.Namespace) -> int:
    """Liveness/readiness probe (JSON). Non-zero when not ready."""
    import json

    from nexo_os.enterprise.observability import readiness

    try:
        from nexo_os.data.factory import get_repository

        repo = get_repository()
    except Exception:  # config-only readiness when a backend is unavailable
        repo = None
    report = readiness(repo=repo)
    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.ready else 1


def _cmd_controls_check(args: argparse.Namespace) -> int:
    """Run the SOC2-style control self-assessment. Non-zero on any FAIL."""
    from nexo_os.enterprise.controls import ControlStatus, render_report, run_controls

    results = run_controls()
    print(render_report(results))
    return 1 if any(r.status == ControlStatus.FAIL for r in results) else 0


def _cmd_security_review(args: argparse.Namespace) -> int:
    """Automated security review. Non-zero when any finding is HIGH or CRITICAL."""
    from nexo_os.enterprise.security_review import gate, render_report, run_security_review

    findings = run_security_review()
    print(render_report(findings))
    return 0 if gate(findings) else 1


def _cmd_data_contract_validate(args: argparse.Namespace) -> int:
    """Validate the active domain source against the canonical data contracts."""
    from datetime import datetime

    from nexo_os.config import DataSource
    from nexo_os.enterprise.data_contracts import duckdb_reader, validate_source

    settings = get_settings()
    if settings.data_source in (DataSource.synthetic, DataSource.gcs):
        reader = duckdb_reader(settings.synthetic_db_path)
    else:
        print(
            f"data-contract-validate: for {settings.data_source.value}, run `nexo bq-validate` "
            "(schema); full contract checks require a duckdb/parquet extract.",
            file=sys.stderr,
        )
        return 2
    as_of = datetime.combine(settings.snapshot_fecha, datetime.min.time())
    results = validate_source(reader, as_of=as_of)
    failed = [r for r in results if not r.ok]
    for r in results:
        mark = "OK " if r.ok else "FAIL"
        extra = "" if r.ok else f" - {'; '.join(r.violations)}"
        print(f"  [{mark}] {r.table} ({r.rows} rows){extra}")
    print(f"data-contract-validate: {len(results) - len(failed)}/{len(results)} contracts passed.")
    return 1 if failed else 0


def _cmd_rotate_secret(args: argparse.Namespace) -> int:
    """Generate a rotation plan for a secret (prints .env values; writes nothing)."""
    from nexo_os.enterprise.secrets import plan_cookie_key_rotation

    if args.secret != "cookie":
        print(f"rotate-secret: unknown secret '{args.secret}'. Supported: cookie.", file=sys.stderr)
        return 2
    plan = plan_cookie_key_rotation()
    print("rotate-secret: set these in .env (previous key stays valid during the grace window):\n")
    print(plan.render())
    print("\nThen redeploy. Clear NEXO_AUTH_COOKIE_KEY_PREVIOUS after the grace window.")
    return 0


def _cmd_iam_validate(args: argparse.Namespace) -> int:
    """Validate the cloud IAM group->role bindings."""
    from nexo_os.enterprise.iam import validate_bindings

    problems = validate_bindings()
    if problems:
        print("iam-validate: problems:\n" + "\n".join(f"  - {p}" for p in problems))
        return 1
    print("iam-validate: OK - bindings are valid.")
    return 0


def _cmd_incident_report(args: argparse.Namespace) -> int:
    """Open an incident: snapshot state, record it to the audit log, print the report."""
    from nexo_os.data.factory import get_repository
    from nexo_os.enterprise.incident import Severity, open_incident, render_incident

    repo = get_repository()
    try:
        incident = open_incident(
            repo, summary=args.summary, severity=Severity(args.severity), opened_by=args.actor
        )
        print(render_incident(incident))
    finally:
        repo.close()
    return 0


def _cmd_release_manifest(args: argparse.Namespace) -> int:
    """Print (or write) the current release manifest."""
    from pathlib import Path

    from nexo_os.enterprise.release import current_manifest, write_manifest

    manifest = write_manifest(Path(args.write)) if args.write else current_manifest()
    if args.write:
        print(f"release-manifest: wrote {args.write}")
    print(manifest.to_json())
    return 0


def _cmd_rollback_check(args: argparse.Namespace) -> int:
    """Check whether rolling back to a target manifest is safe. Non-zero when blocked."""
    from pathlib import Path

    from nexo_os.enterprise.release import load_manifest, plan_rollback

    plan = plan_rollback(load_manifest(Path(args.manifest)))
    if plan.ok:
        print(f"rollback-check: SAFE - {plan.current_version} -> {plan.target_version}.")
        return 0
    print(f"rollback-check: BLOCKED - {plan.current_version} -> {plan.target_version}:")
    for r in plan.reasons:
        print(f"  - {r}")
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nexo", description="Nexo Operating Model v2 task runner.")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("seed", help="Generate synthetic data into the local store.")
    sub.add_parser("bootstrap-admin", help="Provision the initial admin seat from .env.")
    sub.add_parser("run", help="Launch the Streamlit dashboard.")
    sub.add_parser("orchestrate", help="Run one full orchestrator cycle headless.")
    t = sub.add_parser("test", help="Run pytest.")
    t.add_argument("extra", nargs="*", help="Extra args passed to pytest.")
    sub.add_parser("eval", help="Run the eval/guardrail harness (exits non-zero on failure).")
    sub.add_parser("lint", help="Run ruff + black checks.")
    sub.add_parser("bq-validate", help="Validate a live BigQuery dataset vs the canonical DDL.")
    sub.add_parser("turso-seed", help="Load the synthetic dataset into the configured Turso DB.")

    # --- enterprise / production hardening ---
    sub.add_parser("healthcheck", help="Liveness/readiness probe (JSON); non-zero when not ready.")
    sub.add_parser("controls-check", help="SOC2-style control self-assessment (non-zero on FAIL).")
    sub.add_parser("security-review", help="Automated security review (non-zero on HIGH/CRITICAL).")
    sub.add_parser(
        "data-contract-validate", help="Validate the active domain source vs the data contracts."
    )
    rs = sub.add_parser("rotate-secret", help="Generate a rotation plan for a secret.")
    rs.add_argument("secret", nargs="?", default="cookie", help="Which secret (default: cookie).")
    sub.add_parser("iam-validate", help="Validate the cloud IAM group->role bindings.")
    inc = sub.add_parser("incident-report", help="Open an incident: snapshot + audit record.")
    inc.add_argument("--summary", default="Manual incident", help="One-line incident summary.")
    inc.add_argument("--severity", default="SEV2", choices=["SEV1", "SEV2", "SEV3", "SEV4"])
    inc.add_argument("--actor", default="operador", help="Who opened the incident.")
    rm = sub.add_parser("release-manifest", help="Print or write the current release manifest.")
    rm.add_argument("--write", metavar="PATH", help="Write the manifest to this path.")
    rb = sub.add_parser("rollback-check", help="Check whether rolling back to a manifest is safe.")
    rb.add_argument("manifest", help="Path to the target release manifest JSON.")
    return p


_DISPATCH = {
    "seed": _cmd_seed,
    "bootstrap-admin": _cmd_bootstrap_admin,
    "run": _cmd_run,
    "orchestrate": _cmd_orchestrate,
    "test": _cmd_test,
    "eval": _cmd_eval,
    "lint": _cmd_lint,
    "bq-validate": _cmd_bq_validate,
    "turso-seed": _cmd_turso_seed,
    "healthcheck": _cmd_healthcheck,
    "controls-check": _cmd_controls_check,
    "security-review": _cmd_security_review,
    "data-contract-validate": _cmd_data_contract_validate,
    "rotate-secret": _cmd_rotate_secret,
    "iam-validate": _cmd_iam_validate,
    "incident-report": _cmd_incident_report,
    "release-manifest": _cmd_release_manifest,
    "rollback-check": _cmd_rollback_check,
}


def main(argv: list[str] | None = None) -> int:
    # Force UTF-8 on stdout/stderr so Spanish text and report output render on a
    # Windows (cp1252) console instead of raising UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):  # pragma: no cover - stream not reconfigurable
                pass
    configure_logging()
    log = get_logger("cli")
    args = build_parser().parse_args(argv)
    settings = get_settings()
    log.info("cli.start", command=args.command, data_source=settings.data_source.value)
    try:
        return _DISPATCH[args.command](args)
    except Exception as exc:  # fail closed, surface context
        log.error("cli.error", command=args.command, error=str(exc))
        raise
    finally:
        # Release any open Turso libSQL clients (non-daemon worker threads would
        # otherwise block process exit). No-op when the backend isn't Turso.
        try:
            from nexo_os.data.turso import close_all

            close_all()
        except Exception:  # pragma: no cover - shutdown best effort
            pass


if __name__ == "__main__":
    raise SystemExit(main())
