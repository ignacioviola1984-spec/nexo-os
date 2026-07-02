# Observability and monitoring

In-process metrics, health/readiness probes, and structured security events. No external
agent is assumed: metrics render in the Prometheus text exposition format so a sidecar or
scrape can read them, and health/readiness are plain functions a load balancer or
`nexo healthcheck` can call. Everything is PII-free by construction (labels carry
low-cardinality identifiers and counts, never names).

## Metrics

`enterprise/observability.py` holds a process-wide `METRICS` registry. The orchestrator
emits on every cycle:

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `nexo_agent_runs_total` | counter | `estado` | orchestrator cycles, by outcome (ok / con_warnings / error) |
| `nexo_acciones_total` | counter | - | actions produced across runs |
| `nexo_reconciliation_breaks_total` | counter | - | cross-agent reconciliation breaks |
| `nexo_grounding_rejections_total` | counter | - | model prose rejected by the grounding wall |
| `nexo_audit_chain_ok` | gauge | - | 1 if the audit chain verified on the last check |
| `nexo_data_freshness_hours` | gauge | - | age of the domain snapshot at the last run |
| `nexo_security_events_total` | counter | `event` | authn/authz + rotation + incident ticks |

Render for a scrape:

```python
from nexo_os.enterprise.observability import METRICS
print(METRICS.render_prometheus())
```

## Health and readiness

```bash
python -m nexo_os healthcheck   # JSON; exit 0 when ready, 1 when not
```

- **liveness** - process is up and imports cleanly.
- **readiness** - config loads, secret hygiene holds (critical in production), the data
  source is reachable, and the audit chain verifies. A non-critical failure degrades the
  report but still reports ready; a critical failure reports not-ready so the platform
  can pull the instance out of rotation.

## Suggested alerting rules

Wire these in your monitoring platform against the scraped metrics:

- `nexo_audit_chain_ok == 0` -> page (SEV1: audit-integrity break).
- `increase(nexo_agent_runs_total{estado="error"}[15m]) > 0` -> alert.
- `nexo_data_freshness_hours > NEXO_DATA_FRESHNESS_SLA_HOURS` -> alert (stale extract).
- `increase(nexo_reconciliation_breaks_total[1h]) > 0` -> ticket (numbers disagree).
- `increase(nexo_security_events_total{event="login_failed"}[5m]) > 10` -> alert.

## Security events

`emit_security_event(event, actor, **fields)` writes a structured, PII-free log line and
ticks `nexo_security_events_total`. It is called on login success/failure, permission
denials, secret rotation, and incident open, so the security timeline is both logged and
counted.
