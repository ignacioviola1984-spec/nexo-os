"""Cross-platform task runner / entry point: `python -m nexo_os <command>`
(or the `nexo` console script). This is the portable equivalent of the Makefile
targets — `make` is not assumed to be installed.

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
    """DEFERRED: validate a live BigQuery dataset against the canonical DDL."""
    from nexo_os.data.bq_validate import validate

    return validate()


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
    sub.add_parser("bq-validate", help="DEFERRED: validate live BigQuery schema vs DDL.")
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
}


def main(argv: list[str] | None = None) -> int:
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


if __name__ == "__main__":
    raise SystemExit(main())
