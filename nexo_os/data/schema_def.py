"""Canonical schema definition — the single structured source of truth for:
  * the BigQuery DDL (the production contract),
  * the DuckDB DDL (the synthetic dev/test store),
  * the PII field registry (drives redaction), and
  * a contract test that the pydantic models in `models.py` match column-for-column.

The schema is the contract: synthetic data conforms to it exactly, and the future
BigQuery tables match it (same table names, columns, types, grain). Edit here, and
both DDLs plus the model contract test follow.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- Reusable type aliases (bq_type, duck_type) -------------------------------
ID = ("STRING", "VARCHAR")
TEXT = ("STRING", "VARCHAR")
MONEY = ("NUMERIC", "DECIMAL(20, 2)")  # ARS, exact; never float
PCT = ("NUMERIC", "DECIMAL(8, 6)")  # commission fraction, e.g. 0.125 = 12.5%
RATIO = ("FLOAT64", "DOUBLE")  # confidence 0..1; not money
DATE = ("DATE", "DATE")
TS = ("TIMESTAMP", "TIMESTAMP")
INT = ("INT64", "INTEGER")
BOOL = ("BOOL", "BOOLEAN")
JSON = ("JSON", "VARCHAR")  # JSON stored as text in DuckDB (parsed on read)


@dataclass(frozen=True)
class Column:
    name: str
    types: tuple[str, str]  # (bigquery, duckdb)
    nullable: bool = False
    pii: bool = False
    pk: bool = False
    fk: str | None = None  # referenced table name, documentation only
    note: str = ""

    @property
    def bq_type(self) -> str:
        return self.types[0]

    @property
    def duck_type(self) -> str:
        return self.types[1]


@dataclass(frozen=True)
class Table:
    name: str
    grain: str
    columns: list[Column]
    system: bool = False  # written by Nexo itself
    notes: str = ""

    @property
    def pii_columns(self) -> list[str]:
        return [c.name for c in self.columns if c.pii]


# ------------------------------------------------------------------------------
# Domain tables
# ------------------------------------------------------------------------------

CLIENTES = Table(
    name="clientes",
    grain="one row per client",
    columns=[
        Column("cliente_id", ID, pk=True),
        Column("tipo", TEXT, note="persona_fisica | persona_juridica"),
        Column("nombre", TEXT, pii=True),
        Column("documento", TEXT, pii=True, note="CUIT/DNI"),
        Column("fecha_nacimiento", DATE, nullable=True, pii=True),
        Column("email", TEXT, nullable=True, pii=True),
        Column("telefono", TEXT, nullable=True, pii=True),
        Column("localidad", TEXT),
        Column("provincia", TEXT),
        Column("segmento", TEXT),
        Column("fecha_alta", DATE),
        Column("productor_id", ID, fk="productores"),
        Column("estado", TEXT, note="activo | inactivo"),
    ],
)

POLIZAS = Table(
    name="polizas",
    grain="one row per policy",
    columns=[
        Column("poliza_id", ID, pk=True),
        Column("nro_poliza", TEXT),
        Column("cliente_id", ID, fk="clientes"),
        Column("aseguradora_id", ID, fk="aseguradoras"),
        Column(
            "ramo", TEXT, note="auto|hogar|vida|art|caucion|accidentes_personales|comercio|otros"
        ),
        Column("fecha_inicio_vigencia", DATE),
        Column("fecha_fin_vigencia", DATE),
        Column("prima_ars", MONEY),
        Column("suma_asegurada_ars", MONEY),
        Column("estado", TEXT, note="vigente|vencida|anulada|en_gestion|renovada"),
        Column("forma_pago", TEXT),
        Column("frecuencia_pago", TEXT, note="mensual|trimestral|semestral|anual"),
        Column("comision_pct", PCT, note="decimal fraction; 0.15 = 15%"),
        Column("productor_id", ID, fk="productores"),
        Column(
            "poliza_origen_id",
            ID,
            nullable=True,
            fk="polizas",
            note="prior-term policy (renewal chain)",
        ),
    ],
)

CUOTAS = Table(
    name="cuotas",
    grain="one row per installment of a policy's payment plan",
    columns=[
        Column("cuota_id", ID, pk=True),
        Column("poliza_id", ID, fk="polizas"),
        Column("nro_cuota", INT),
        Column("fecha_vencimiento", DATE),
        Column("monto_ars", MONEY),
        Column("estado", TEXT, note="pendiente|pagada|vencida|parcial"),
        Column("fecha_pago", DATE, nullable=True),
        Column("monto_pagado_ars", MONEY, note="0 when unpaid"),
    ],
    notes="dias_mora and bucket_mora are DERIVED at read-time relative to the run "
    "snapshot date (see core.morosidad); they are NOT stored columns.",
)

COMISIONES = Table(
    name="comisiones",
    grain="one row per commission accrual/settlement event (policy x period)",
    columns=[
        Column("comision_id", ID, pk=True),
        Column("poliza_id", ID, fk="polizas"),
        Column("aseguradora_id", ID, fk="aseguradoras"),
        Column("periodo", TEXT, note="YYYY-MM"),
        Column("base_comisionable_ars", MONEY),
        Column("comision_pct", PCT),
        Column("comision_esperada_ars", MONEY),
        Column("comision_liquidada_ars", MONEY, nullable=True),
        Column("fecha_liquidacion", DATE, nullable=True),
        Column("estado", TEXT, note="esperada|liquidada|parcial|con_diferencia"),
        Column("diferencia_ars", MONEY, note="esperada - liquidada (settled portion)"),
    ],
)

LEADS = Table(
    name="leads",
    grain="one row per sales opportunity",
    columns=[
        Column("lead_id", ID, pk=True),
        Column("fecha_ingreso", DATE),
        Column("nombre_prospecto", TEXT, pii=True),
        Column("contacto", TEXT, pii=True, note="phone/email of prospect"),
        Column("canal_origen", TEXT, note="referido|web|redes|llamado|otro"),
        Column("ramo", TEXT),
        Column("productor_id", ID, fk="productores"),
        Column("estado", TEXT, note="nuevo|contactado|cotizado|presentado|ganado|perdido"),
        Column("fecha_ultimo_movimiento", DATE),
        Column("fecha_cierre", DATE, nullable=True),
        Column("motivo_perdida", TEXT, nullable=True),
        Column("cliente_id", ID, nullable=True, fk="clientes", note="set when won"),
    ],
)

COTIZACIONES = Table(
    name="cotizaciones",
    grain="one row per quote issued for a lead",
    columns=[
        Column("cotizacion_id", ID, pk=True),
        Column("lead_id", ID, fk="leads"),
        Column("aseguradora_id", ID, fk="aseguradoras"),
        Column("ramo", TEXT),
        Column("prima_cotizada_ars", MONEY),
        Column("fecha_cotizacion", DATE),
        Column("estado", TEXT, note="emitida|presentada|aceptada|rechazada|vencida"),
        Column("vigencia_cotizacion", DATE, nullable=True),
        Column(
            "poliza_id", ID, nullable=True, fk="polizas", note="set when bound -> quote-to-bind"
        ),
    ],
)

SINIESTROS = Table(
    name="siniestros",
    grain="one row per claim",
    columns=[
        Column("siniestro_id", ID, pk=True),
        Column("poliza_id", ID, fk="polizas"),
        Column("fecha", DATE),
        Column("tipo", TEXT),
        Column("monto_reclamado_ars", MONEY),
        Column("monto_pagado_ars", MONEY, nullable=True),
        Column("estado", TEXT, note="abierto|en_proceso|pagado|rechazado|cerrado"),
    ],
)

ASEGURADORAS = Table(
    name="aseguradoras",
    grain="reference: one row per insurer",
    columns=[
        Column("aseguradora_id", ID, pk=True),
        Column("nombre", TEXT),
        Column("condiciones_comision_json", JSON, note="commission terms by ramo"),
    ],
)

PRODUCTORES = Table(
    name="productores",
    grain="reference: one row per broker seat/agent",
    columns=[
        Column("productor_id", ID, pk=True),
        Column("nombre", TEXT),
        Column("equipo", TEXT),
        Column("activo", BOOL),
    ],
)

INTERACCIONES = Table(
    name="interacciones",
    grain="one row per interaction with a client or lead",
    columns=[
        Column("interaccion_id", ID, pk=True),
        Column("entidad_tipo", TEXT, note="cliente | lead"),
        Column("entidad_id", ID),
        Column("fecha", DATE),
        Column("tipo", TEXT, note="llamado|email|visita|nota"),
        Column("resumen", TEXT),
    ],
)

# ------------------------------------------------------------------------------
# System tables (written by Nexo itself)
# ------------------------------------------------------------------------------

ACCIONES = Table(
    name="acciones",
    grain="one row per proposed action (the HITL inbox)",
    system=True,
    columns=[
        Column("accion_id", ID, pk=True),
        Column("agente", TEXT),
        Column("tipo_accion", TEXT),
        Column("entidad_tipo", TEXT),
        Column("entidad_id", ID),
        Column("prioridad", TEXT, note="alta|media|baja"),
        Column("confianza", RATIO, note="0..1, deterministic"),
        Column("monto_en_juego_ars", MONEY, nullable=True),
        Column("rationale_json", JSON, note="the deterministic numbers behind the action"),
        Column("mensaje_es", TEXT, note="model-drafted Spanish message/recommendation"),
        Column("estado", TEXT, note="propuesta|aprobada|rechazada|editada|vencida"),
        Column("creada_en", TS),
        Column("resuelta_en", TS, nullable=True),
        Column("resuelta_por", ID, nullable=True),
        Column("nota_revisor", TEXT, nullable=True),
        Column("run_id", ID, fk="agent_runs"),
    ],
)

AGENT_RUNS = Table(
    name="agent_runs",
    grain="one row per orchestrator/agent run",
    system=True,
    columns=[
        Column("run_id", ID, pk=True),
        Column("iniciado_en", TS),
        Column("finalizado_en", TS, nullable=True),
        Column("estado", TEXT, note="ok|con_warnings|error"),
        Column("resumen_json", JSON),
        Column("data_source", TEXT, note="synthetic|bigquery"),
        Column("data_snapshot_fecha", DATE),
    ],
)

AUDIT_LOG = Table(
    name="audit_log",
    grain="one row per event (append-only, hash-chained)",
    system=True,
    columns=[
        Column("evento_id", ID, pk=True),
        Column("ts", TS),
        Column("actor", TEXT, note="system | user id"),
        Column("accion", TEXT),
        Column("entidad_tipo", TEXT),
        Column("entidad_id", ID, nullable=True),
        Column("detalle_json", JSON, note="identifiers only, never full PII"),
        Column("prev_hash", TEXT, nullable=True),
        Column("hash", TEXT),
    ],
)


DOMAIN_TABLES: list[Table] = [
    CLIENTES,
    POLIZAS,
    CUOTAS,
    COMISIONES,
    LEADS,
    COTIZACIONES,
    SINIESTROS,
    ASEGURADORAS,
    PRODUCTORES,
    INTERACCIONES,
]

SYSTEM_TABLES: list[Table] = [ACCIONES, AGENT_RUNS, AUDIT_LOG]

ALL_TABLES: list[Table] = DOMAIN_TABLES + SYSTEM_TABLES

TABLES_BY_NAME: dict[str, Table] = {t.name: t for t in ALL_TABLES}

# PII registry: table -> set of PII column names. Drives the redaction helper.
PII_FIELDS: dict[str, set[str]] = {t.name: set(t.pii_columns) for t in ALL_TABLES}


# ------------------------------------------------------------------------------
# DDL renderers
# ------------------------------------------------------------------------------


def _render_ddl(tables: list[Table], dialect: str, qualify: str = "") -> str:
    """Render CREATE TABLE statements. dialect in {'bigquery', 'duckdb'}."""
    out: list[str] = []
    for t in tables:
        pk = [c.name for c in t.columns if c.pk]
        has_pk_clause = dialect == "duckdb" and bool(pk)
        # Build each column's "name type [NOT NULL]" plus its optional note. The
        # separating comma MUST come before any inline '--' comment, otherwise the
        # comment swallows the comma and the statement is invalid SQL.
        defs = []
        for c in t.columns:
            sql_type = c.bq_type if dialect == "bigquery" else c.duck_type
            null = "" if c.nullable else " NOT NULL"
            defs.append((f"  {c.name} {sql_type}{null}", c.note))
        lines = []
        last_idx = len(defs) - 1
        for i, (coldef, note) in enumerate(defs):
            trailing_comma = i < last_idx or has_pk_clause
            line = coldef + ("," if trailing_comma else "")
            if note:
                line += f"  -- {note}"
            lines.append(line)
        if has_pk_clause:
            lines.append(f"  PRIMARY KEY ({', '.join(pk)})")
        body = "\n".join(lines)
        name = f"{qualify}{t.name}" if qualify else t.name
        header = f"-- grain: {t.grain}"
        if t.notes:
            header += f"\n-- note: {t.notes}"
        stmt = f"{header}\nCREATE TABLE IF NOT EXISTS {name} (\n{body}\n);"
        out.append(stmt)
    return "\n\n".join(out) + "\n"


def render_bigquery_ddl(qualify: str = "") -> str:
    """Canonical BigQuery DDL. `qualify` e.g. 'project.dataset.' for fully-qualified."""
    return _render_ddl(ALL_TABLES, "bigquery", qualify)


def render_duckdb_ddl() -> str:
    return _render_ddl(ALL_TABLES, "duckdb")
