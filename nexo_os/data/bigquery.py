"""BigQueryRepository — the production data source.

Implements the same NexoRepository interface against BigQuery using the canonical
table names and the same SQL semantics as the synthetic backend. Synthetic is the
default (chosen for PII and client-confidentiality reasons); BigQuery is selected via
configuration:

  * It is selected with NEXO_DATA_SOURCE=bigquery.
  * If selected without the google-cloud-bigquery library, a project, and credentials,
    it FAILS CLOSED with a clear message. It never fabricates or stubs results.

To activate: `pip install -e ".[bigquery]"`, set NEXO_BQ_PROJECT / NEXO_BQ_DATASET
/ NEXO_BQ_CREDENTIALS_PATH, run `python -m nexo_os bq-validate`, then set
NEXO_DATA_SOURCE=bigquery. No agent or core code changes.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

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
from nexo_os.data.schema_def import TABLES_BY_NAME


def _cols(table: str) -> list[str]:
    return [c.name for c in TABLES_BY_NAME[table].columns]


class BigQueryRepository(NexoRepository):
    data_source = "bigquery"

    def __init__(self, snapshot_fecha: date | None = None) -> None:
        settings = get_settings()
        self._snapshot = snapshot_fecha or settings.snapshot_fecha
        self._project = settings.bq_project
        self._dataset = settings.bq_dataset
        cred_path = settings.bq_credentials_path

        if not self._project:
            raise DataSourceUnavailable(
                "BigQuery backend selected but NEXO_BQ_PROJECT is not set. Failing closed."
            )
        try:
            from google.cloud import bigquery  # type: ignore
            from google.oauth2 import service_account  # type: ignore
        except ImportError as exc:  # library not installed
            raise DataSourceUnavailable(
                "BigQuery backend selected but google-cloud-bigquery is not installed. "
                'Install with: pip install -e ".[bigquery]". Failing closed.'
            ) from exc

        if cred_path is not None:
            if not cred_path.exists():
                raise DataSourceUnavailable(
                    f"BigQuery credentials file not found at {cred_path}. Failing closed."
                )
            creds = service_account.Credentials.from_service_account_file(str(cred_path))
            self._client = bigquery.Client(project=self._project, credentials=creds)
        else:
            # Fall back to Application Default Credentials; raises if none present.
            self._client = bigquery.Client(project=self._project)
        self._bigquery = bigquery

    # --- helpers --------------------------------------------------------------

    def _fqtn(self, table: str) -> str:
        return f"`{self._project}.{self._dataset}.{table}`"

    def _query(
        self,
        table: str,
        model: type[_Base],
        where: Sequence[str] = (),
        params: Sequence[object] = (),
        order_by: str | None = None,
    ) -> list:
        cols = ", ".join(_cols(table))
        sql = f"SELECT {cols} FROM {self._fqtn(table)}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        if order_by:
            sql += f" ORDER BY {order_by}"
        job_config = self._bigquery.QueryJobConfig(
            query_parameters=[
                self._bigquery.ScalarQueryParameter(None, _bq_type(p), p) for p in params
            ]
        )
        rows = self._client.query(sql, job_config=job_config).result()
        names = _cols(table)
        return [model(**{n: row[n] for n in names}) for row in rows]

    @staticmethod
    def _eq(col: str, value: object, where: list[str], params: list[object]) -> None:
        if value is not None:
            where.append(f"{col} = ?")
            params.append(str(value) if hasattr(value, "value") else value)

    @property
    def snapshot_fecha(self) -> date:
        return self._snapshot

    # --- domain reads ---------------------------------------------------------

    def get_clientes(self, estado: ClienteEstado | None = None) -> list[Cliente]:
        where: list[str] = []
        params: list[object] = []
        self._eq("estado", estado, where, params)
        return self._query("clientes", Cliente, where, params)

    def get_polizas(
        self, estado: PolizaEstado | None = None, ramo: Ramo | None = None
    ) -> list[Poliza]:
        where: list[str] = []
        params: list[object] = []
        self._eq("estado", estado, where, params)
        self._eq("ramo", ramo, where, params)
        return self._query("polizas", Poliza, where, params)

    def get_cuotas(self, estado: CuotaEstado | None = None) -> list[Cuota]:
        where: list[str] = []
        params: list[object] = []
        self._eq("estado", estado, where, params)
        return self._query("cuotas", Cuota, where, params)

    def get_comisiones(
        self, periodo: str | None = None, estado: ComisionEstado | None = None
    ) -> list[Comision]:
        where: list[str] = []
        params: list[object] = []
        self._eq("periodo", periodo, where, params)
        self._eq("estado", estado, where, params)
        return self._query("comisiones", Comision, where, params)

    def get_leads(self, estado: LeadEstado | None = None) -> list[Lead]:
        where: list[str] = []
        params: list[object] = []
        self._eq("estado", estado, where, params)
        return self._query("leads", Lead, where, params)

    def get_cotizaciones(self, estado: CotizacionEstado | None = None) -> list[Cotizacion]:
        where: list[str] = []
        params: list[object] = []
        self._eq("estado", estado, where, params)
        return self._query("cotizaciones", Cotizacion, where, params)

    def get_siniestros(self, estado: SiniestroEstado | None = None) -> list[Siniestro]:
        where: list[str] = []
        params: list[object] = []
        self._eq("estado", estado, where, params)
        return self._query("siniestros", Siniestro, where, params)

    def get_aseguradoras(self) -> list[Aseguradora]:
        return self._query("aseguradoras", Aseguradora)

    def get_productores(self) -> list[Productor]:
        return self._query("productores", Productor)

    def get_interacciones(self, entidad_tipo: EntidadTipo | None = None) -> list[Interaccion]:
        where: list[str] = []
        params: list[object] = []
        self._eq("entidad_tipo", entidad_tipo, where, params)
        return self._query("interacciones", Interaccion, where, params)

    # --- system tables --------------------------------------------------------

    def _insert_rows(self, table: str, items: Sequence[_Base]) -> None:
        if not items:
            return
        rows = [{c: _json_safe(getattr(it, c)) for c in _cols(table)} for it in items]
        errors = self._client.insert_rows_json(f"{self._project}.{self._dataset}.{table}", rows)
        if errors:
            raise DataSourceUnavailable(f"BigQuery insert into {table} failed: {errors}")

    def insert_acciones(self, acciones: list[Accion]) -> None:
        self._insert_rows("acciones", acciones)

    def get_acciones(
        self, estado: AccionEstado | None = None, run_id: str | None = None
    ) -> list[Accion]:
        where: list[str] = []
        params: list[object] = []
        self._eq("estado", estado, where, params)
        self._eq("run_id", run_id, where, params)
        return self._query("acciones", Accion, where, params, order_by="creada_en")

    def get_accion(self, accion_id: str) -> Accion | None:
        rows = self._query("acciones", Accion, ["accion_id = ?"], [accion_id])
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
        sets = "estado = @estado, resuelta_en = @resuelta_en, resuelta_por = @resuelta_por, nota_revisor = @nota"
        qp = [
            self._bigquery.ScalarQueryParameter("estado", "STRING", str(estado)),
            self._bigquery.ScalarQueryParameter("resuelta_en", "TIMESTAMP", resuelta_en),
            self._bigquery.ScalarQueryParameter("resuelta_por", "STRING", resuelta_por),
            self._bigquery.ScalarQueryParameter("nota", "STRING", nota_revisor),
            self._bigquery.ScalarQueryParameter("accion_id", "STRING", accion_id),
        ]
        if mensaje_es is not None:
            sets += ", mensaje_es = @mensaje_es"
            qp.append(self._bigquery.ScalarQueryParameter("mensaje_es", "STRING", mensaje_es))
        sql = f"UPDATE {self._fqtn('acciones')} SET {sets} WHERE accion_id = @accion_id"
        self._client.query(
            sql, job_config=self._bigquery.QueryJobConfig(query_parameters=qp)
        ).result()

    def insert_agent_run(self, run: AgentRun) -> None:
        self._insert_rows("agent_runs", [run])

    def update_agent_run(
        self, run_id: str, finalizado_en: datetime, estado: RunEstado, resumen_json: str
    ) -> None:
        qp = [
            self._bigquery.ScalarQueryParameter("finalizado_en", "TIMESTAMP", finalizado_en),
            self._bigquery.ScalarQueryParameter("estado", "STRING", str(estado)),
            self._bigquery.ScalarQueryParameter("resumen_json", "STRING", resumen_json),
            self._bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
        ]
        sql = (
            f"UPDATE {self._fqtn('agent_runs')} SET finalizado_en = @finalizado_en, "
            "estado = @estado, resumen_json = @resumen_json WHERE run_id = @run_id"
        )
        self._client.query(
            sql, job_config=self._bigquery.QueryJobConfig(query_parameters=qp)
        ).result()

    def get_agent_runs(self) -> list[AgentRun]:
        return self._query("agent_runs", AgentRun, order_by="iniciado_en")

    def append_audit_event(self, event: AuditEvent) -> None:
        self._insert_rows("audit_log", [event])

    def get_audit_events(self) -> list[AuditEvent]:
        return self._query("audit_log", AuditEvent, order_by="ts")

    def get_last_audit_hash(self) -> str | None:
        sql = f"SELECT hash FROM {self._fqtn('audit_log')} ORDER BY ts DESC LIMIT 1"
        rows = list(self._client.query(sql).result())
        return rows[0]["hash"] if rows else None


def _bq_type(value: object) -> str:
    from datetime import date as _d
    from datetime import datetime as _dt
    from decimal import Decimal

    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT64"
    if isinstance(value, Decimal):
        return "NUMERIC"
    if isinstance(value, _dt):
        return "TIMESTAMP"
    if isinstance(value, _d):
        return "DATE"
    return "STRING"


def _json_safe(value: object) -> object:
    """Coerce a model attribute to a JSON-serializable value for insert_rows_json."""
    from datetime import date as _d
    from datetime import datetime as _dt
    from decimal import Decimal

    if value is None:
        return None
    if hasattr(value, "value"):  # StrEnum
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (_dt, _d)):
        return value.isoformat()
    return value
