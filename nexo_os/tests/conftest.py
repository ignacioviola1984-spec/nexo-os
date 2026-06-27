"""Shared fixtures: a minimal synthetic repository backed by temp DuckDB stores."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from nexo_os.data.synthetic import SyntheticRepository, init_synthetic_store


def _seed_minimal(path: Path) -> None:
    con = duckdb.connect(str(path))
    init_synthetic_store(con)
    con.execute("INSERT INTO productores VALUES (?, ?, ?, ?)", ["PRD-01", "P", "Equipo", True])
    con.execute(
        "INSERT INTO clientes (cliente_id, tipo, nombre, documento, fecha_nacimiento, email, "
        "telefono, localidad, provincia, segmento, fecha_alta, productor_id, estado) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
    con.execute(
        "INSERT INTO polizas (poliza_id, nro_poliza, cliente_id, aseguradora_id, ramo, "
        "fecha_inicio_vigencia, fecha_fin_vigencia, prima_ars, suma_asegurada_ars, estado, "
        "forma_pago, frecuencia_pago, comision_pct, productor_id, poliza_origen_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
    # current-period commission so cartera<->comisiones reconciliation is clean
    con.execute(
        "INSERT INTO comisiones (comision_id, poliza_id, aseguradora_id, periodo, "
        "base_comisionable_ars, comision_pct, comision_esperada_ars, comision_liquidada_ars, "
        "fecha_liquidacion, estado, diferencia_ars) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            "COM1",
            "POL1",
            "ASEG-01",
            "2026-06",
            Decimal("100000.00"),
            Decimal("0.120000"),
            Decimal("12000.00"),
            Decimal("12000.00"),
            date(2026, 6, 20),
            "liquidada",
            Decimal("0.00"),
        ],
    )
    # recent interaction so retention does not flag the client on inactivity
    con.execute(
        "INSERT INTO interacciones (interaccion_id, entidad_tipo, entidad_id, fecha, tipo, resumen) "
        "VALUES (?,?,?,?,?,?)",
        ["INT1", "cliente", "C1", date(2026, 6, 1), "llamado", "ok"],
    )
    con.close()


@pytest.fixture
def repo(tmp_path: Path) -> SyntheticRepository:
    dom = tmp_path / "dom.duckdb"
    rt = tmp_path / "rt.duckdb"
    _seed_minimal(dom)
    return SyntheticRepository(
        synthetic_db_path=dom, runtime_db_path=rt, snapshot_fecha=date(2026, 6, 30)
    )
