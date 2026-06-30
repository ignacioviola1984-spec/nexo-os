"""TursoRepository against a local libSQL file (no network/secrets needed).

Exercises the round-trip that matters most for a money system: Decimal amounts and
dates stored as TEXT must come back byte-exact through the pydantic models, and the
hash-chained audit log must verify. Skipped when libsql-client is not installed.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("libsql_client")

from nexo_os.audit import AuditWriter, verify_chain  # noqa: E402
from nexo_os.data.models import (  # noqa: E402
    Accion,
    AccionEstado,
    AgentRun,
    Prioridad,
    RunEstado,
)
from nexo_os.data.schema_def import ALL_TABLES  # noqa: E402
from nexo_os.data.turso import TursoRepository, _ddl_statements, _param  # noqa: E402

SNAPSHOT = date(2026, 6, 30)


def _file_url(tmp_path: Path) -> str:
    return "file:" + str(tmp_path / "turso.db").replace("\\", "/")


def _seed_minimal(url: str) -> None:
    """Mirror conftest._seed_minimal for the SQLite dialect: one clean policy whose
    current-period commission keeps the cartera<->comisiones reconciliation tied."""
    import libsql_client

    client = libsql_client.create_client_sync(url=url)
    for stmt in _ddl_statements(ALL_TABLES):
        client.execute(stmt)

    def ins(table: str, cols: list[str], values: list[object]) -> None:
        ph = ", ".join("?" for _ in cols)
        client.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph})",
            [_param(v) for v in values],
        )

    ins("productores", ["productor_id", "nombre", "equipo", "activo"], ["PRD-01", "P", "Eq", True])
    ins(
        "clientes",
        [
            "cliente_id",
            "tipo",
            "nombre",
            "documento",
            "fecha_nacimiento",
            "email",
            "telefono",
            "localidad",
            "provincia",
            "segmento",
            "fecha_alta",
            "productor_id",
            "estado",
        ],
        [
            "C1",
            "persona_fisica",
            "Juan Perez",
            "20-99000001-0",
            date(1980, 1, 1),
            "c1@example.com",
            "+54-11-40000000",
            "Lomas",
            "Buenos Aires",
            "retail",
            date(2020, 1, 1),
            "PRD-01",
            "activo",
        ],
    )
    ins(
        "polizas",
        [
            "poliza_id",
            "nro_poliza",
            "cliente_id",
            "aseguradora_id",
            "ramo",
            "fecha_inicio_vigencia",
            "fecha_fin_vigencia",
            "prima_ars",
            "suma_asegurada_ars",
            "estado",
            "forma_pago",
            "frecuencia_pago",
            "comision_pct",
            "productor_id",
            "poliza_origen_id",
        ],
        [
            "POL1",
            "AUTO-1",
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
    client.close()


@pytest.fixture
def turso_repo(tmp_path: Path):
    url = _file_url(tmp_path)
    _seed_minimal(url)
    repo = TursoRepository(database_url=url, auth_token=None, snapshot_fecha=SNAPSHOT)
    yield repo
    repo.close()  # the sync libSQL client holds a loop thread; close to let the process exit


def test_domain_reads_and_decimal_is_exact(turso_repo: TursoRepository) -> None:
    polizas = turso_repo.get_polizas()
    assert len(polizas) == 1
    p = polizas[0]
    # money round-trips byte-exact as Decimal, never coerced to float
    assert p.prima_ars == Decimal("100000.00")
    assert isinstance(p.prima_ars, Decimal)
    assert p.comision_pct == Decimal("0.120000")
    assert p.fecha_fin_vigencia == date(2026, 12, 31)
    # bool stored as 0/1 comes back as bool
    assert turso_repo.get_productores()[0].activo is True
    # filtered read
    assert turso_repo.get_polizas(estado=None, ramo=None)[0].poliza_id == "POL1"


def test_acciones_insert_get_resolve(turso_repo: TursoRepository) -> None:
    accion = Accion(
        accion_id="A1",
        agente="cartera",
        tipo_accion="revisar",
        entidad_tipo="poliza",
        entidad_id="POL1",
        prioridad=Prioridad.alta,
        confianza=0.9,
        monto_en_juego_ars=Decimal("123456.78"),
        rationale_json="{}",
        mensaje_es="hola",
        estado=AccionEstado.propuesta,
        creada_en=datetime(2026, 6, 30, 10, 0, 0),
        resuelta_en=None,
        resuelta_por=None,
        nota_revisor=None,
        run_id="RUN1",
    )
    turso_repo.insert_acciones([accion])
    got = turso_repo.get_accion("A1")
    assert got is not None
    assert got.monto_en_juego_ars == Decimal("123456.78")  # exact through TEXT
    assert turso_repo.get_acciones(estado=AccionEstado.propuesta)[0].accion_id == "A1"

    turso_repo.resolve_accion(
        "A1", AccionEstado.aprobada, datetime(2026, 6, 30, 11, 0, 0), "user-1", "ok"
    )
    resolved = turso_repo.get_accion("A1")
    assert resolved.estado is AccionEstado.aprobada
    assert resolved.resuelta_por == "user-1"


def test_agent_run_and_audit_chain_verifies(turso_repo: TursoRepository) -> None:
    run = AgentRun(
        run_id="RUN1",
        iniciado_en=datetime(2026, 6, 30, 9, 0, 0),
        finalizado_en=None,
        estado=RunEstado.ok,
        resumen_json="{}",
        data_source="turso",
        data_snapshot_fecha=SNAPSHOT,
    )
    turso_repo.insert_agent_run(run)
    turso_repo.update_agent_run("RUN1", datetime(2026, 6, 30, 9, 5, 0), RunEstado.ok, "{}")
    assert turso_repo.get_agent_runs()[0].finalizado_en == datetime(2026, 6, 30, 9, 5, 0)

    writer = AuditWriter(turso_repo)
    writer.record("system", "run.start", "agent_run", "RUN1", {"k": "v"})
    writer.record("user-1", "accion.aprobada", "accion", "A1", {"accion_id": "A1"})
    events = turso_repo.get_audit_events()
    assert len(events) == 2
    assert verify_chain(events).ok  # hash chain links correctly across appends


def test_fails_closed_without_url() -> None:
    from nexo_os.data.repository import DataSourceUnavailable

    with pytest.raises(DataSourceUnavailable):
        TursoRepository(database_url="", auth_token=None, snapshot_fecha=SNAPSHOT)
