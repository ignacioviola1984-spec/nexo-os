"""TursoRepository — a libSQL/SQLite backend, usable two ways:

  * as a full domain+system backend (NEXO_DATA_SOURCE=turso), the hosted parallel
    to BigQuery, seeded with `nexo turso-seed`; or
  * as the system-table store only (NEXO_SYSTEM_STORE=turso) behind a
    CompositeRepository, so approvals and the hash-chained audit log persist across
    Streamlit Cloud restarts while domain stays on synthetic/BigQuery.

One client serves both a local `file:` database (dev/CI, no token) and a remote
`libsql://` Turso database (URL + auth token). SQLite has no exact NUMERIC, so money
is stored as TEXT (the Decimal's string form) and coerced back to Decimal by the
pydantic models on read — see schema_def for the dialect mapping. Fails closed: if
the client library is missing or the URL is unset, it raises DataSourceUnavailable
rather than fabricating data.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

from nexo_os.config import get_settings
from nexo_os.data.models import (
    Accion,
    AccionEstado,
    AgentRun,
    Aseguradora,
    AuditEvent,
    Cliente,
    ClienteEstado,
    Comision,
    ComisionEstado,
    Cotizacion,
    CotizacionEstado,
    Cuota,
    CuotaEstado,
    EntidadTipo,
    Interaccion,
    Lead,
    LeadEstado,
    Poliza,
    PolizaEstado,
    Productor,
    Ramo,
    RunEstado,
    Siniestro,
    SiniestroEstado,
    _Base,
)
from nexo_os.data.repository import DataSourceUnavailable, NexoRepository
from nexo_os.data.schema_def import SYSTEM_TABLES, TABLES_BY_NAME, Table

# The sync libSQL client runs a non-daemon worker thread that blocks interpreter
# exit until the client is closed. Long-lived hosts (Streamlit) keep one cached
# client for the process lifetime; short-lived CLI commands must close it on the way
# out. We track open clients here so cli.main() can release them in a finally.
_OPEN_CLIENTS: list = []


def close_all() -> None:
    """Close every open Turso client so a CLI process can exit cleanly."""
    for client in list(_OPEN_CLIENTS):
        try:
            client.close()
        except Exception:  # pragma: no cover - best effort on shutdown
            pass
    _OPEN_CLIENTS.clear()


def _cols(table: str) -> list[str]:
    return [c.name for c in TABLES_BY_NAME[table].columns]


def _ddl_statements(tables: Sequence[Table]) -> list[str]:
    """Plain `CREATE TABLE IF NOT EXISTS` statements (one per table) for libSQL —
    executed individually since the client runs a single statement per call."""
    stmts: list[str] = []
    for t in tables:
        cols = ", ".join(
            f"{c.name} {c.sqlite_type}{'' if c.nullable else ' NOT NULL'}" for c in t.columns
        )
        pk = [c.name for c in t.columns if c.pk]
        pk_clause = f", PRIMARY KEY ({', '.join(pk)})" if pk else ""
        stmts.append(f"CREATE TABLE IF NOT EXISTS {t.name} ({cols}{pk_clause})")
    return stmts


def _param(value: object) -> object:
    """Coerce a model attribute to a libSQL-friendly bind parameter."""
    if value is None:
        return None
    if isinstance(value, bool):  # before int: bool is an int subclass
        return int(value)
    if isinstance(value, Decimal):
        return str(value)  # exact; never float
    if isinstance(value, (datetime, date)):
        return value.isoformat()  # ISO text sorts chronologically
    if hasattr(value, "value"):  # StrEnum -> its string value
        return value.value
    return value


class TursoRepository(NexoRepository):
    data_source = "turso"

    def __init__(
        self,
        database_url: str | None = None,
        auth_token: str | None = None,
        snapshot_fecha: date | None = None,
    ) -> None:
        settings = get_settings()
        url = database_url or settings.turso_database_url
        token = auth_token or settings.turso_auth_token
        self._snapshot = snapshot_fecha or settings.snapshot_fecha

        if not url:
            raise DataSourceUnavailable(
                "Turso backend selected but NEXO_TURSO_DATABASE_URL is not set. Failing closed."
            )
        try:
            import libsql_client
        except ImportError as exc:  # pragma: no cover - import guard
            raise DataSourceUnavailable(
                "Turso backend selected but libsql-client is not installed. "
                'Install with: pip install -e ".[turso]". Failing closed.'
            ) from exc

        self._libsql = libsql_client
        kwargs: dict[str, object] = {"url": url}
        if token:
            kwargs["auth_token"] = token
        try:
            self._client = libsql_client.create_client_sync(**kwargs)
            _OPEN_CLIENTS.append(self._client)
            # System tables are created idempotently so system-only/hybrid use needs
            # no seeded domain tables. Harmless when this is a full backend too.
            for stmt in _ddl_statements(SYSTEM_TABLES):
                self._client.execute(stmt)
        except Exception as exc:  # pragma: no cover - connection guard
            raise DataSourceUnavailable(f"Could not open Turso database at {url}: {exc}") from exc

    @property
    def snapshot_fecha(self) -> date:
        return self._snapshot

    # --- generic helpers ------------------------------------------------------

    def _rows_to_models(self, rs, model: type[_Base]) -> list:
        names = list(rs.columns)
        return [model(**dict(zip(names, row, strict=True))) for row in rs.rows]

    def _select(
        self,
        table: str,
        model: type[_Base],
        where: Sequence[str] = (),
        params: Sequence[object] = (),
        order_by: str | None = None,
    ) -> list:
        cols = ", ".join(_cols(table))
        sql = f"SELECT {cols} FROM {table}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        if order_by:
            sql += f" ORDER BY {order_by}"
        try:
            rs = self._client.execute(sql, list(params))
        except Exception as exc:
            msg = str(exc).lower()
            if "no such table" in msg:
                raise DataSourceUnavailable(
                    f"Turso table '{table}' does not exist. Run `nexo turso-seed` first."
                ) from exc
            raise
        return self._rows_to_models(rs, model)

    @staticmethod
    def _eq(col: str, value: object, where: list[str], params: list[object]) -> None:
        if value is not None:
            where.append(f"{col} = ?")
            params.append(_param(value))

    def _insert(self, table: str, items: Sequence[_Base]) -> None:
        if not items:
            return
        cols = _cols(table)
        placeholders = ", ".join("?" for _ in cols)
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        self._client.batch([(sql, [_param(getattr(it, c)) for c in cols]) for it in items])

    # --- domain reads ---------------------------------------------------------

    def get_clientes(self, estado: ClienteEstado | None = None) -> list[Cliente]:
        where: list[str] = []
        params: list[object] = []
        self._eq("estado", estado, where, params)
        return self._select("clientes", Cliente, where, params)

    def get_polizas(
        self, estado: PolizaEstado | None = None, ramo: Ramo | None = None
    ) -> list[Poliza]:
        where: list[str] = []
        params: list[object] = []
        self._eq("estado", estado, where, params)
        self._eq("ramo", ramo, where, params)
        return self._select("polizas", Poliza, where, params)

    def get_cuotas(self, estado: CuotaEstado | None = None) -> list[Cuota]:
        where: list[str] = []
        params: list[object] = []
        self._eq("estado", estado, where, params)
        return self._select("cuotas", Cuota, where, params)

    def get_comisiones(
        self, periodo: str | None = None, estado: ComisionEstado | None = None
    ) -> list[Comision]:
        where: list[str] = []
        params: list[object] = []
        self._eq("periodo", periodo, where, params)
        self._eq("estado", estado, where, params)
        return self._select("comisiones", Comision, where, params)

    def get_leads(self, estado: LeadEstado | None = None) -> list[Lead]:
        where: list[str] = []
        params: list[object] = []
        self._eq("estado", estado, where, params)
        return self._select("leads", Lead, where, params)

    def get_cotizaciones(self, estado: CotizacionEstado | None = None) -> list[Cotizacion]:
        where: list[str] = []
        params: list[object] = []
        self._eq("estado", estado, where, params)
        return self._select("cotizaciones", Cotizacion, where, params)

    def get_siniestros(self, estado: SiniestroEstado | None = None) -> list[Siniestro]:
        where: list[str] = []
        params: list[object] = []
        self._eq("estado", estado, where, params)
        return self._select("siniestros", Siniestro, where, params)

    def get_aseguradoras(self) -> list[Aseguradora]:
        return self._select("aseguradoras", Aseguradora)

    def get_productores(self) -> list[Productor]:
        return self._select("productores", Productor)

    def get_interacciones(self, entidad_tipo: EntidadTipo | None = None) -> list[Interaccion]:
        where: list[str] = []
        params: list[object] = []
        self._eq("entidad_tipo", entidad_tipo, where, params)
        return self._select("interacciones", Interaccion, where, params)

    # --- acciones (HITL inbox) ------------------------------------------------

    def insert_acciones(self, acciones: list[Accion]) -> None:
        self._insert("acciones", acciones)

    def get_acciones(
        self, estado: AccionEstado | None = None, run_id: str | None = None
    ) -> list[Accion]:
        where: list[str] = []
        params: list[object] = []
        self._eq("estado", estado, where, params)
        self._eq("run_id", run_id, where, params)
        return self._select("acciones", Accion, where, params, order_by="creada_en")

    def get_accion(self, accion_id: str) -> Accion | None:
        rows = self._select("acciones", Accion, ["accion_id = ?"], [accion_id])
        return rows[0] if rows else None

    def resolve_accion(
        self,
        accion_id: str,
        estado: AccionEstado,
        resuelta_en: datetime,
        resuelta_por: str,
        nota_revisor: str | None = None,
        mensaje_es: str | None = None,
    ) -> None:
        if mensaje_es is None:
            self._client.execute(
                "UPDATE acciones SET estado = ?, resuelta_en = ?, resuelta_por = ?, "
                "nota_revisor = ? WHERE accion_id = ?",
                [_param(estado), _param(resuelta_en), resuelta_por, nota_revisor, accion_id],
            )
        else:
            self._client.execute(
                "UPDATE acciones SET estado = ?, resuelta_en = ?, resuelta_por = ?, "
                "nota_revisor = ?, mensaje_es = ? WHERE accion_id = ?",
                [
                    _param(estado),
                    _param(resuelta_en),
                    resuelta_por,
                    nota_revisor,
                    mensaje_es,
                    accion_id,
                ],
            )

    # --- agent_runs -----------------------------------------------------------

    def insert_agent_run(self, run: AgentRun) -> None:
        self._insert("agent_runs", [run])

    def update_agent_run(
        self, run_id: str, finalizado_en: datetime, estado: RunEstado, resumen_json: str
    ) -> None:
        self._client.execute(
            "UPDATE agent_runs SET finalizado_en = ?, estado = ?, resumen_json = ? "
            "WHERE run_id = ?",
            [_param(finalizado_en), _param(estado), resumen_json, run_id],
        )

    def get_agent_runs(self) -> list[AgentRun]:
        return self._select("agent_runs", AgentRun, order_by="iniciado_en")

    # --- audit_log (append-only, hash-chained) --------------------------------

    def append_audit_event(self, event: AuditEvent) -> None:
        self._insert("audit_log", [event])

    def get_audit_events(self) -> list[AuditEvent]:
        return self._select("audit_log", AuditEvent, order_by="rowid")

    def get_last_audit_hash(self) -> str | None:
        rs = self._client.execute("SELECT hash FROM audit_log ORDER BY rowid DESC LIMIT 1")
        return rs.rows[0][0] if rs.rows else None

    # --- maintenance ----------------------------------------------------------

    def close(self) -> None:
        try:
            self._client.close()
        finally:
            try:
                _OPEN_CLIENTS.remove(self._client)
            except ValueError:
                pass
