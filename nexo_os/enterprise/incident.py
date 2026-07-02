"""Incident response tooling.

When something goes wrong, the first job is a trustworthy snapshot of state. ``open_incident``
captures it: audit-chain integrity, the last run's status, readiness probes, and the
metrics snapshot - then records the incident to the (hash-chained) audit log so the
response itself is on the record. It renders a Markdown report to paste into the incident
channel. The runbook (severities, roles, comms) lives in docs/INCIDENT_RESPONSE.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from nexo_os.clock import now


class Severity(StrEnum):
    SEV1 = "SEV1"  # broker cannot operate / integrity break / data exposure
    SEV2 = "SEV2"  # major function degraded, no clean workaround
    SEV3 = "SEV3"  # minor/partial degradation
    SEV4 = "SEV4"  # cosmetic / informational


@dataclass(frozen=True)
class IncidentSnapshot:
    audit_chain_ok: bool
    audit_broken_at: int | None
    audit_events: int
    last_run_estado: str | None
    runs_total: int
    ready: bool
    health_checks: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Incident:
    id: str
    severity: Severity
    summary: str
    opened_by: str
    opened_at: datetime
    snapshot: IncidentSnapshot


def _incident_id(ts: datetime) -> str:
    return "INC-" + ts.strftime("%Y%m%d-%H%M%S")


def capture_snapshot(repo, settings=None) -> IncidentSnapshot:
    from nexo_os.audit import verify_chain
    from nexo_os.enterprise.observability import METRICS, readiness

    events = repo.get_audit_events()
    v = verify_chain(events)
    runs = repo.get_agent_runs()
    last_estado = None
    if runs:
        last = runs[-1]
        last_estado = getattr(getattr(last, "estado", None), "value", None) or getattr(
            last, "estado", None
        )
    report = readiness(repo=repo, settings=settings)
    return IncidentSnapshot(
        audit_chain_ok=v.ok,
        audit_broken_at=v.broken_at,
        audit_events=v.total,
        last_run_estado=str(last_estado) if last_estado is not None else None,
        runs_total=len(runs),
        ready=report.ready,
        health_checks=[{"name": c.name, "ok": c.ok, "detail": c.detail} for c in report.checks],
        metrics=METRICS.snapshot(),
    )


def open_incident(
    repo,
    summary: str,
    severity: Severity = Severity.SEV2,
    opened_by: str = "operador",
    settings=None,
) -> Incident:
    """Capture a state snapshot and record the incident to the audit log."""
    from nexo_os.audit import AuditWriter
    from nexo_os.enterprise.observability import emit_security_event

    ts = now()
    snapshot = capture_snapshot(repo, settings)
    incident = Incident(
        id=_incident_id(ts),
        severity=severity,
        summary=summary,
        opened_by=opened_by,
        opened_at=ts,
        snapshot=snapshot,
    )
    emit_security_event(
        "incident_opened", actor=opened_by, incident=incident.id, sev=severity.value
    )
    try:
        AuditWriter(repo).record(
            actor=opened_by,
            accion="incident_opened",
            entidad_tipo="incident",
            entidad_id=incident.id,
            detalle={
                "severity": severity.value,
                "summary": summary,
                "audit_chain_ok": snapshot.audit_chain_ok,
                "ready": snapshot.ready,
            },
            ts=ts,
        )
    except Exception:  # pragma: no cover - never let recording block the response
        pass
    return incident


def render_incident(incident: Incident) -> str:
    s = incident.snapshot
    chain = "OK" if s.audit_chain_ok else f"BROKEN at index {s.audit_broken_at}"
    lines = [
        f"# {incident.id} - {incident.severity.value}",
        "",
        f"- Summary: {incident.summary}",
        f"- Opened by: {incident.opened_by}",
        f"- Opened at: {incident.opened_at.isoformat()}",
        "",
        "## State snapshot",
        f"- Audit chain: {chain} ({s.audit_events} events)",
        f"- Last run estado: {s.last_run_estado or 'n/a'} ({s.runs_total} runs)",
        f"- Readiness: {'ready' if s.ready else 'NOT ready'}",
        "",
        "### Health checks",
    ]
    for c in s.health_checks:
        lines.append(f"- {'OK' if c['ok'] else 'X'} {c['name']}: {c['detail']}")
    lines += ["", "See docs/INCIDENT_RESPONSE.md for severities, roles, and comms."]
    return "\n".join(lines) + "\n"
