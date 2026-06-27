"""Phase 6: the full orchestrator cycle persists acciones/agent_runs/audit and keeps
the audit chain intact. Runs offline (no API key -> deterministic grounded facts)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexo_os.audit import verify_chain
from nexo_os.config import Settings
from nexo_os.data.ground_truth import ground_truth_path
from nexo_os.data.models import RunEstado
from nexo_os.orchestrator import run_cycle

OFFLINE = Settings(ANTHROPIC_API_KEY=None)


def test_run_cycle_persists_and_audits(repo) -> None:
    ctx = run_cycle(repo=repo, settings=OFFLINE)

    # run recorded and finalized, with no reconciliation breaks on clean data
    runs = repo.get_agent_runs()
    assert len(runs) == 1
    assert runs[0].finalizado_en is not None
    assert runs[0].estado is RunEstado.ok
    assert ctx.warnings == []

    # acciones persisted == proposed; every one narrated (deterministic facts here)
    persisted = repo.get_acciones()
    assert len(persisted) == len(ctx.acciones)
    assert all(a.mensaje_es for a in persisted)

    # audit chain: run_started + run_finished present and intact
    events = repo.get_audit_events()
    kinds = {e.accion for e in events}
    assert {"run_started", "run_finished"} <= kinds
    assert verify_chain(events).ok


def test_run_cycle_marks_warnings_on_reconciliation_break(tmp_path: Path) -> None:
    """A vigente policy with NO current-period commission breaks the cartera<->comisiones
    reconciliation -> the run is marked con_warnings (fail loud, not silently averaged)."""
    from datetime import date
    from decimal import Decimal

    import duckdb

    from nexo_os.data.synthetic import SyntheticRepository, init_synthetic_store

    dom = tmp_path / "dom.duckdb"
    con = duckdb.connect(str(dom))
    init_synthetic_store(con)
    con.execute("INSERT INTO productores VALUES (?,?,?,?)", ["PRD-01", "P", "E", True])
    con.execute(
        "INSERT INTO polizas (poliza_id, nro_poliza, cliente_id, aseguradora_id, ramo, "
        "fecha_inicio_vigencia, fecha_fin_vigencia, prima_ars, suma_asegurada_ars, estado, "
        "forma_pago, frecuencia_pago, comision_pct, productor_id, poliza_origen_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            "POL1",
            "A-1",
            "C1",
            "ASEG-01",
            "auto",
            date(2026, 1, 1),
            date(2026, 12, 31),
            Decimal("100000.00"),
            Decimal("1000000.00"),
            "vigente",
            "debito",
            "mensual",
            Decimal("0.120000"),
            "PRD-01",
            None,
        ],
    )
    con.close()
    repo = SyntheticRepository(
        synthetic_db_path=dom,
        runtime_db_path=tmp_path / "rt.duckdb",
        snapshot_fecha=date(2026, 6, 30),
    )
    ctx = run_cycle(repo=repo, settings=OFFLINE)
    assert ctx.warnings
    assert repo.get_agent_runs()[-1].estado is RunEstado.con_warnings


@pytest.mark.skipif(not ground_truth_path().exists(), reason="run `python -m nexo_os seed` first")
def test_run_cycle_on_seeded_store_clean(tmp_path: Path) -> None:
    """Full seeded book: reconciliations hold (estado ok) and many actions are proposed."""
    from nexo_os.config import get_settings
    from nexo_os.data.synthetic import SyntheticRepository

    s = get_settings()
    repo = SyntheticRepository(
        synthetic_db_path=s.synthetic_db_path,
        runtime_db_path=tmp_path / "rt.duckdb",
        snapshot_fecha=s.synthetic_snapshot_fecha,
    )
    ctx = run_cycle(repo=repo, settings=OFFLINE)
    assert ctx.warnings == []
    assert len(ctx.acciones) > 20
    assert repo.get_agent_runs()[-1].estado is RunEstado.ok
    assert verify_chain(repo.get_audit_events()).ok
