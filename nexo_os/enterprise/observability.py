"""Production observability: a metrics registry, health/readiness probes, and a
structured security-event emitter.

No external agent or exporter is assumed. Metrics live in-process and render in the
Prometheus text exposition format, so a sidecar/scrape or the dashboard can read them;
health/readiness are plain functions a load balancer or `nexo healthcheck` can call.
Everything is deterministic and PII-free (labels carry identifiers/counts, never names).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime

from nexo_os.clock import now
from nexo_os.logging_setup import get_logger

log = get_logger("observability")

# --- metrics ------------------------------------------------------------------


def _key(name: str, labels: dict[str, str] | None) -> tuple:
    return (name, tuple(sorted((labels or {}).items())))


class MetricsRegistry:
    """Minimal, thread-safe counter/gauge registry with Prometheus text output.

    Counters only increase; gauges are set to a value. Labels are low-cardinality
    (agent id, estado, data_source) - never per-client identifiers.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple, float] = {}
        self._gauges: dict[tuple, float] = {}
        self._help: dict[str, str] = {}

    def describe(self, name: str, help_text: str) -> None:
        self._help[name] = help_text

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        if value < 0:
            raise ValueError("counter increment must be non-negative")
        with self._lock:
            self._counters[_key(name, labels)] = self._counters.get(_key(name, labels), 0.0) + value

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        with self._lock:
            self._gauges[_key(name, labels)] = float(value)

    def get_counter(self, name: str, **labels: str) -> float:
        with self._lock:
            return self._counters.get(_key(name, labels), 0.0)

    def get_gauge(self, name: str, **labels: str) -> float | None:
        with self._lock:
            return self._gauges.get(_key(name, labels))

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            return {
                "counters": {self._fmt(k): v for k, v in self._counters.items()},
                "gauges": {self._fmt(k): v for k, v in self._gauges.items()},
            }

    @staticmethod
    def _fmt(k: tuple) -> str:
        name, labels = k
        if not labels:
            return name
        inner = ",".join(f'{lk}="{lv}"' for lk, lv in labels)
        return f"{name}{{{inner}}}"

    def render_prometheus(self) -> str:
        """Prometheus text exposition (v0.0.4). Stable ordering for reproducibility."""
        lines: list[str] = []
        with self._lock:
            emitted_help: set[str] = set()

            def emit(kind: str, store: dict[tuple, float]) -> None:
                for k in sorted(store, key=self._fmt):
                    name = k[0]
                    if name not in emitted_help:
                        if name in self._help:
                            lines.append(f"# HELP {name} {self._help[name]}")
                        lines.append(f"# TYPE {name} {kind}")
                        emitted_help.add(name)
                    lines.append(f"{self._fmt(k)} {store[k]:g}")

            emit("counter", self._counters)
            emit("gauge", self._gauges)
        return "\n".join(lines) + ("\n" if lines else "")


#: Process-wide default registry.
METRICS = MetricsRegistry()
METRICS.describe("nexo_agent_runs_total", "Orchestrator cycles started, by estado.")
METRICS.describe("nexo_acciones_total", "Actions produced by a run, by estado.")
METRICS.describe("nexo_reconciliation_breaks_total", "Cross-agent reconciliation breaks.")
METRICS.describe("nexo_grounding_rejections_total", "Model prose rejected by the grounding wall.")
METRICS.describe("nexo_audit_chain_ok", "1 if the audit chain verified on the last check, else 0.")
METRICS.describe("nexo_data_freshness_hours", "Age of the domain snapshot in hours at last run.")


# --- health / readiness -------------------------------------------------------


@dataclass(frozen=True)
class HealthCheck:
    name: str
    ok: bool
    detail: str
    critical: bool = True  # a non-critical failure degrades but does not fail readiness


@dataclass(frozen=True)
class HealthReport:
    ok: bool
    ready: bool
    checks: list[HealthCheck] = field(default_factory=list)
    ts: datetime = field(default_factory=now)
    version: str = ""
    environment: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "ready": self.ready,
            "ts": self.ts.isoformat(),
            "version": self.version,
            "environment": self.environment,
            "checks": [
                {"name": c.name, "ok": c.ok, "detail": c.detail, "critical": c.critical}
                for c in self.checks
            ],
        }


def liveness() -> HealthCheck:
    """Process is up and the module imports cleanly."""
    return HealthCheck("liveness", True, "process alive")


def readiness(repo=None, settings=None) -> HealthReport:
    """Probe whether the service can actually serve a request.

    Runs config, secret-hygiene, data-source and audit-chain probes. `repo` is
    optional - without it the data/audit probes are skipped (config-only readiness).
    """
    from nexo_os.config import get_settings

    settings = settings or get_settings()
    checks: list[HealthCheck] = [liveness()]

    # Secret hygiene (critical in production only).
    from nexo_os.enterprise.secrets import cookie_key_is_weak

    weak = cookie_key_is_weak(settings.auth_cookie_key)
    checks.append(
        HealthCheck(
            "secret_hygiene",
            ok=not (weak and settings.is_production),
            detail="weak auth cookie key" if weak else "cookie key set",
            critical=settings.is_production,
        )
    )

    # Data source + audit chain (only when a repo is available).
    if repo is not None:
        try:
            _ = repo.snapshot_fecha
            checks.append(HealthCheck("data_source", True, f"{repo.data_source} reachable"))
        except Exception as exc:  # pragma: no cover - defensive
            checks.append(HealthCheck("data_source", False, f"unreachable: {exc}"))
        try:
            from nexo_os.audit import verify_chain

            v = verify_chain(repo.get_audit_events())
            METRICS.set_gauge("nexo_audit_chain_ok", 1.0 if v.ok else 0.0)
            checks.append(
                HealthCheck(
                    "audit_chain",
                    ok=v.ok,
                    detail="intact" if v.ok else f"broken at index {v.broken_at}",
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            checks.append(HealthCheck("audit_chain", False, f"verify failed: {exc}"))

    critical_failures = [c for c in checks if c.critical and not c.ok]
    any_failure = [c for c in checks if not c.ok]
    return HealthReport(
        ok=not any_failure,
        ready=not critical_failures,
        checks=checks,
        version=settings.service_version,
        environment=settings.environment.value,
    )


# --- structured security events ----------------------------------------------


def emit_security_event(event: str, actor: str = "system", **fields: object) -> None:
    """Structured, PII-free security log line + a metric tick. Use for authn/authz
    decisions, permission denials, rotations, and control failures."""
    METRICS.inc("nexo_security_events_total", event=event)
    # 'event' is structlog's positional message key, so pass the event name as 'name'.
    log.info("security_event", name=event, actor=actor, **fields)
