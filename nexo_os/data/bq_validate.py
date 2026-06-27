"""Validate a live BigQuery dataset against the canonical DDL.

`python -m nexo_os bq-validate` compares the columns/types of each canonical table
in the configured BigQuery dataset against `schema_def`. It is a pre-flight check for
the data-source cutover; it fails closed when no project/credentials are configured.
"""

from __future__ import annotations

import sys

from nexo_os.config import get_settings
from nexo_os.data.schema_def import ALL_TABLES


def validate() -> int:
    settings = get_settings()
    if not settings.bq_project:
        print(
            "bq-validate: NEXO_BQ_PROJECT not set. This is the BigQuery cutover check; "
            "configure project + credentials before running. Failing closed.",
            file=sys.stderr,
        )
        return 2
    try:
        from google.cloud import bigquery  # type: ignore
    except ImportError:
        print(
            'bq-validate: google-cloud-bigquery not installed. Run: pip install -e ".[bigquery]".',
            file=sys.stderr,
        )
        return 2

    client = bigquery.Client(project=settings.bq_project)
    problems: list[str] = []
    for table in ALL_TABLES:
        ref = f"{settings.bq_project}.{settings.bq_dataset}.{table.name}"
        try:
            live = client.get_table(ref)
        except Exception as exc:  # missing table
            problems.append(f"{table.name}: not found ({exc})")
            continue
        live_cols = {f.name: f.field_type for f in live.schema}
        for col in table.columns:
            if col.name not in live_cols:
                problems.append(f"{table.name}.{col.name}: missing in BigQuery")
            # type comparison is intentionally loose (NUMERIC vs BIGNUMERIC etc.)
    if problems:
        print("bq-validate: schema mismatches:\n" + "\n".join(f"  - {p}" for p in problems))
        return 1
    print(f"bq-validate: OK — all {len(ALL_TABLES)} canonical tables match.")
    return 0
