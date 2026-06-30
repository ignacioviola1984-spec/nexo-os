"""GcsRepository — a cloud-storage data source (Google Cloud Storage).

The brokerage's domain extracts are dropped into a GCS bucket as Parquet (one
object per canonical table, e.g. gs://<bucket>/<prefix>clientes.parquet). On start
this repository downloads those objects into a local DuckDB domain store and then
behaves exactly like the synthetic backend (it subclasses it): same reads, same
writable runtime store for system tables (acciones, agent_runs, audit_log).

Selected with NEXO_DATA_SOURCE=gcs. FAILS CLOSED (never stubs results) if the
bucket is unset, the google-cloud-storage library is missing, or credentials are
invalid — the same standard as the BigQuery backend.

Activate: `pip install -e ".[gcs]"`, set NEXO_GCS_BUCKET / NEXO_GCS_PREFIX /
NEXO_GCS_CREDENTIALS_PATH, then NEXO_DATA_SOURCE=gcs. No agent or core changes.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import date
from pathlib import Path

import duckdb

from nexo_os.config import get_settings
from nexo_os.data.repository import DataSourceUnavailable
from nexo_os.data.schema_def import DOMAIN_TABLES
from nexo_os.data.synthetic import SyntheticRepository


class GcsRepository(SyntheticRepository):
    data_source = "gcs"

    def __init__(self, snapshot_fecha: date | None = None, prefix: str | None = None) -> None:
        settings = get_settings()
        if not settings.gcs_bucket:
            raise DataSourceUnavailable(
                "GCS backend selected but NEXO_GCS_BUCKET is not set. Failing closed."
            )
        try:
            from google.cloud import storage  # type: ignore
        except ImportError as exc:
            raise DataSourceUnavailable(
                "GCS backend selected but google-cloud-storage is not installed. "
                'Install with: pip install -e ".[gcs]". Failing closed.'
            ) from exc

        prefix = prefix if prefix is not None else settings.gcs_prefix
        cred_path = settings.gcs_credentials_path
        if cred_path is not None:
            if not cred_path.exists():
                raise DataSourceUnavailable(
                    f"GCS credentials file not found at {cred_path}. Failing closed."
                )
            client = storage.Client.from_service_account_json(str(cred_path))
        else:
            client = storage.Client()  # Application Default Credentials; raises if none

        self._tmpdir = Path(tempfile.mkdtemp(prefix="nexo-gcs-"))
        domain_store = self._materialize_domain(client, settings.gcs_bucket, prefix)

        # Behave as the synthetic backend over the downloaded domain store; system
        # tables (writable) go to the configured runtime store.
        super().__init__(
            synthetic_db_path=domain_store,
            runtime_db_path=settings.runtime_db_path,
            snapshot_fecha=snapshot_fecha,
        )

    def _materialize_domain(self, client, bucket_name: str, prefix: str) -> Path:
        """Download each domain table's Parquet object and load it into a local
        DuckDB store with the canonical schema. Fails closed if an object is absent."""
        bucket = client.bucket(bucket_name)
        store = self._tmpdir / "domain.duckdb"
        con = duckdb.connect(str(store))
        try:
            for table in DOMAIN_TABLES:
                blob_name = f"{prefix}{table.name}.parquet"
                blob = bucket.blob(blob_name)
                if not blob.exists():
                    raise DataSourceUnavailable(
                        f"GCS object gs://{bucket_name}/{blob_name} not found. Failing closed."
                    )
                local_parquet = self._tmpdir / f"{table.name}.parquet"
                blob.download_to_filename(str(local_parquet))
                con.execute(
                    f"CREATE TABLE {table.name} AS "
                    f"SELECT * FROM read_parquet('{local_parquet.as_posix()}')"
                )
        finally:
            con.close()
        return store

    def close(self) -> None:
        super().close()
        shutil.rmtree(self._tmpdir, ignore_errors=True)
