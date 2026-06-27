"""SyntheticRepository contract: typed reads (money stays Decimal), filters, and the
system-table read/write paths (acciones, agent_runs, audit_log)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from nexo_os.data.models import (
    Accion,
    AccionEstado,
    AgentRun,
    AuditEvent,
    ClienteEstado,
    Prioridad,
    RunEstado,
)
from nexo_os.data.synthetic import SyntheticRepository, init_synthetic_store


def _seed_domain(path: Path) -> None:
    con = duckdb.connect(str(path))
    init_synthetic_store(con)
    con.execute(
        "INSERT INTO productores VALUES (?, ?, ?, ?)",
        ["P1", "Productor Uno", "Equipo A", True],
    )
    # two clients: one activo, one inactivo
    con.executemany(
        "INSERT INTO clientes (cliente_id, tipo, nombre, documento, fecha_nacimiento, "
        "email, telefono, localidad, provincia, segmento, fecha_alta, productor_id, estado) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            [
                "C1",
                "persona_fisica",
                "Cliente Activo",
                "20-00000001-3",
                date(1980, 1, 1),
                "c1@example.com",
                "+540000000001",
                "Lomas",
                "Buenos Aires",
                "retail",
                date(2020, 1, 1),
                "P1",
                "activo",
            ],
            [
                "C2",
                "persona_fisica",
                "Cliente Inactivo",
                "20-00000002-1",
                date(1975, 5, 5),
                "c2@example.com",
                "+540000000002",
                "Banfield",
                "Buenos Aires",
                "retail",
                date(2019, 1, 1),
                "P1",
                "inactivo",
            ],
        ],
    )
    con.execute(
        "INSERT INTO polizas (poliza_id, nro_poliza, cliente_id, aseguradora_id, ramo, "
        "fecha_inicio_vigencia, fecha_fin_vigencia, prima_ars, suma_asegurada_ars, estado, "
        "forma_pago, frecuencia_pago, comision_pct, productor_id, poliza_origen_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "POL1",
            "AUTO-1",
            "C1",
            "A1",
            "auto",
            date(2026, 1, 1),
            date(2026, 12, 31),
            Decimal("123456.78"),
            Decimal("5000000.00"),
            "vigente",
            "debito",
            "mensual",
            Decimal("0.150000"),
            "P1",
            None,
        ],
    )
    con.close()


@pytest.fixture
def repo(tmp_path: Path) -> SyntheticRepository:
    dom = tmp_path / "dom.duckdb"
    rt = tmp_path / "rt.duckdb"
    _seed_domain(dom)
    return SyntheticRepository(
        synthetic_db_path=dom, runtime_db_path=rt, snapshot_fecha=date(2026, 6, 30)
    )


def test_missing_store_fails_closed(tmp_path: Path) -> None:
    from nexo_os.data.repository import DataSourceUnavailable

    with pytest.raises(DataSourceUnavailable):
        SyntheticRepository(
            synthetic_db_path=tmp_path / "nope.duckdb", runtime_db_path=tmp_path / "rt.duckdb"
        )


def test_reads_return_typed_models(repo: SyntheticRepository) -> None:
    clientes = repo.get_clientes()
    assert len(clientes) == 2
    assert {c.cliente_id for c in clientes} == {"C1", "C2"}


def test_money_stays_decimal(repo: SyntheticRepository) -> None:
    pol = repo.get_polizas()[0]
    assert isinstance(pol.prima_ars, Decimal)
    assert pol.prima_ars == Decimal("123456.78")
    assert pol.comision_pct == Decimal("0.150000")


def test_filter_by_estado(repo: SyntheticRepository) -> None:
    activos = repo.get_clientes(estado=ClienteEstado.activo)
    assert [c.cliente_id for c in activos] == ["C1"]


def test_snapshot_fecha(repo: SyntheticRepository) -> None:
    assert repo.snapshot_fecha == date(2026, 6, 30)


def test_acciones_roundtrip_and_resolve(repo: SyntheticRepository) -> None:
    accion = Accion(
        accion_id="ACC1",
        agente="cobranza",
        tipo_accion="gestionar_cobro",
        entidad_tipo="cliente",
        entidad_id="C1",
        prioridad=Prioridad.alta,
        confianza=0.9,
        monto_en_juego_ars=Decimal("123456.78"),
        rationale_json='{"monto": "123456.78"}',
        mensaje_es="Gestionar cobro pendiente.",
        estado=AccionEstado.propuesta,
        creada_en=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
        resuelta_en=None,
        resuelta_por=None,
        nota_revisor=None,
        run_id="RUN1",
    )
    repo.insert_acciones([accion])
    fetched = repo.get_accion("ACC1")
    assert fetched is not None
    assert fetched.estado is AccionEstado.propuesta
    assert isinstance(fetched.monto_en_juego_ars, Decimal)

    repo.resolve_accion(
        "ACC1",
        AccionEstado.aprobada,
        resuelta_en=datetime(2026, 6, 30, 13, 0, tzinfo=UTC),
        resuelta_por="admin",
        nota_revisor="OK",
    )
    resolved = repo.get_accion("ACC1")
    assert resolved is not None and resolved.estado is AccionEstado.aprobada
    assert resolved.resuelta_por == "admin"
    assert [a.accion_id for a in repo.get_acciones(estado=AccionEstado.aprobada)] == ["ACC1"]


def test_agent_run_lifecycle(repo: SyntheticRepository) -> None:
    run = AgentRun(
        run_id="RUN1",
        iniciado_en=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
        finalizado_en=None,
        estado=RunEstado.ok,
        resumen_json="{}",
        data_source="synthetic",
        data_snapshot_fecha=date(2026, 6, 30),
    )
    repo.insert_agent_run(run)
    repo.update_agent_run(
        "RUN1", datetime(2026, 6, 30, 12, 5, tzinfo=UTC), RunEstado.con_warnings, '{"warnings": 1}'
    )
    runs = repo.get_agent_runs()
    assert len(runs) == 1 and runs[0].estado is RunEstado.con_warnings


def test_audit_append_only_and_chain_tip(repo: SyntheticRepository) -> None:
    assert repo.get_last_audit_hash() is None
    e1 = AuditEvent(
        evento_id="E1",
        ts=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
        actor="system",
        accion="run_started",
        entidad_tipo="run",
        entidad_id="RUN1",
        detalle_json="{}",
        prev_hash=None,
        hash="h1",
    )
    e2 = AuditEvent(
        evento_id="E2",
        ts=datetime(2026, 6, 30, 12, 1, tzinfo=UTC),
        actor="admin",
        accion="accion_aprobada",
        entidad_tipo="accion",
        entidad_id="ACC1",
        detalle_json="{}",
        prev_hash="h1",
        hash="h2",
    )
    repo.append_audit_event(e1)
    repo.append_audit_event(e2)
    assert repo.get_last_audit_hash() == "h2"
    events = repo.get_audit_events()
    assert [e.evento_id for e in events] == ["E1", "E2"]  # insertion order preserved
