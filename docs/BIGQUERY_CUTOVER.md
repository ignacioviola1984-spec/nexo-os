# BigQuery cutover runbook (deferred)

Switching Nexo from synthetic data to the production BigQuery source is **config +
credentials against the documented schema — no change to agent or core code**. This is
deliberately deferred in this build; the BigQuery backend is scaffolded and fails
closed until configured.

## Preconditions
- A BigQuery dataset whose tables match the canonical schema exactly (same names,
  columns, types, grain). The contract is `nexo_os/data/schema/ddl_bigquery.sql`
  (generated from `schema_def.py`; regenerate with `python scripts/render_ddl.py`).
- A GCP service account with read on the domain tables and read/write on the system
  tables (`acciones`, `agent_runs`, `audit_log`).

## Steps

1. **Install the optional backend**
   ```bash
   pip install -e ".[bigquery]"
   ```

2. **Create the dataset + tables** from the canonical DDL (replace the unqualified
   names with `project.dataset.`-qualified names):
   ```bash
   bq mk --dataset <project>:nexo
   # apply nexo_os/data/schema/ddl_bigquery.sql
   ```

3. **Configure credentials + target** in `.env`:
   ```
   NEXO_BQ_PROJECT=<project>
   NEXO_BQ_DATASET=nexo
   NEXO_BQ_CREDENTIALS_PATH=gcp-credentials.json   # gitignored
   ```

4. **Validate the live schema against the contract** (does not flip the source):
   ```bash
   python -m nexo_os bq-validate
   ```
   This checks every canonical table/column exists in the dataset. Fix mismatches
   before proceeding. It fails closed (exit 2) if project/credentials are absent.

5. **Flip the source**:
   ```
   NEXO_DATA_SOURCE=bigquery
   ```

6. **Smoke test** headless:
   ```bash
   python -m nexo_os orchestrate
   ```
   Confirm the run completes, reconciliations hold, and `agent_runs`/`audit_log` rows
   land in BigQuery.

## Notes
- `data_snapshot_fecha` should be set (`NEXO_SNAPSHOT_FECHA`) to the intended "as of"
  date; all aging/expiry is computed relative to it.
- The synthetic generator and ground-truth files do not apply to live data; the eval
  harness's numbers/detection suites are calibrated to the synthetic dataset and should
  be pointed at a BigQuery fixture dataset before being used as a live gate.
- Make `audit_log` physically append-only at the database level (see SECURITY.md) — the
  hash chain is tamper-evidence, not prevention.
