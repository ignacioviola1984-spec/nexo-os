"""Hybrid mode: domain reads from synthetic DuckDB, system tables in Turso.

Proves the CompositeRepository keeps domain and system on different backends — the
shape behind NEXO_SYSTEM_STORE=turso, which lets approvals and the audit log survive
the ephemeral filesystem of a Streamlit Cloud restart. Skipped without libsql-client.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("libsql_client")

from nexo_os.audit import AuditWriter, verify_chain  # noqa: E402
from nexo_os.data.composite import CompositeRepository  # noqa: E402
from nexo_os.data.models import Accion, AccionEstado, Prioridad  # noqa: E402
from nexo_os.data.synthetic import SyntheticRepository  # noqa: E402
from nexo_os.data.turso import TursoRepository  # noqa: E402


def _accion() -> Accion:
    return Accion(
        accion_id="A1",
        agente="cartera",
        tipo_accion="revisar",
        entidad_tipo="poliza",
        entidad_id="POL1",
        prioridad=Prioridad.media,
        confianza=0.8,
        monto_en_juego_ars=Decimal("9999.99"),
        rationale_json="{}",
        mensaje_es="x",
        estado=AccionEstado.propuesta,
        creada_en=datetime(2026, 6, 30, 10, 0, 0),
        resuelta_en=None,
        resuelta_por=None,
        nota_revisor=None,
        run_id="RUN1",
    )


def test_composite_splits_domain_and_system(repo: SyntheticRepository, tmp_path: Path) -> None:
    url = "file:" + str(tmp_path / "sys.db").replace("\\", "/")
    system = TursoRepository(database_url=url, auth_token=None, snapshot_fecha=date(2026, 6, 30))
    composite = CompositeRepository(domain=repo, system=system)
    try:
        assert composite.data_source == "synthetic+turso"
        # domain read served by synthetic DuckDB
        assert composite.get_polizas()[0].poliza_id == "POL1"

        # system writes land in Turso, not the synthetic runtime store
        composite.insert_acciones([_accion()])
        assert composite.get_accion("A1").monto_en_juego_ars == Decimal("9999.99")
        assert system.get_accion("A1") is not None  # confirms it is in the Turso store

        writer = AuditWriter(composite)
        writer.record("system", "run.start", "agent_run", "RUN1", {})
        writer.record("user-1", "accion.aprobada", "accion", "A1", {})
        assert verify_chain(composite.get_audit_events()).ok
    finally:
        system.close()  # release the libSQL loop thread
