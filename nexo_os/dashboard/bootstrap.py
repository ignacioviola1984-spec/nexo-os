"""Make a public demo self-bootstrapping (Streamlit Community Cloud).

On first container start the synthetic store, the users file, and the runtime store do
not exist. `ensure_demo_ready` creates them idempotently so the deployed demo comes up
with data and a usable login, with zero manual setup. It only acts when something is
missing — subsequent reruns are no-ops.

This path only runs synthetic data; it never touches a real backend.
"""

from __future__ import annotations

from nexo_os.config import get_settings
from nexo_os.logging_setup import get_logger

log = get_logger("demo")


def ensure_demo_ready() -> None:
    settings = get_settings()

    # 1) synthetic data
    if not settings.synthetic_db_path.exists():
        from nexo_os.data.generate import generate_and_load

        log.info("demo.seeding")
        generate_and_load()

    # 2) a usable login — only when auth is enabled. The public demo (demo_mode) has
    #    open access, so no users file is needed.
    if not settings.demo_mode and settings.admin_password:
        from nexo_os.security import users as user_store

        if not user_store.load_users().get("usernames"):
            user_store.bootstrap_admin()
            log.info("demo.admin_bootstrapped", username=settings.admin_username)

    # 3) one orchestration so the inbox is populated on first view
    from nexo_os.data.synthetic import SyntheticRepository
    from nexo_os.orchestrator import run_cycle

    repo = SyntheticRepository(
        synthetic_db_path=settings.synthetic_db_path,
        runtime_db_path=settings.runtime_db_path,
        snapshot_fecha=settings.snapshot_fecha,
    )
    try:
        if not repo.get_agent_runs():
            log.info("demo.initial_run")
            run_cycle(repo=repo, settings=settings)
    finally:
        repo.close()
