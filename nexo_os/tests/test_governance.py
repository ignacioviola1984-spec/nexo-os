"""Phase 4: confidence/priority determinism, maker-checker resolution, hash-chained
audit (incl. tamper detection), and PII redaction."""

from __future__ import annotations

from decimal import Decimal

import pytest

from nexo_os.agents.base import build_accion, confidence, priority
from nexo_os.audit import AuditWriter, verify_chain
from nexo_os.config import Thresholds
from nexo_os.core.results import Hallazgo
from nexo_os.data.models import AccionEstado, Prioridad
from nexo_os.review import ReviewError, resolve_accion
from nexo_os.security.pii import cliente_safe_context, redact
from nexo_os.tests import factories as f

T = Thresholds()


# --- confidence / priority -----------------------------------------------------


def test_confidence_blend() -> None:
    assert confidence(_h(completitud=1.0, senial=1.0)) == 1.0
    assert confidence(_h(completitud=0.5, senial=0.7)) == 0.6


def test_priority_amount_driven() -> None:
    assert priority(Decimal("600000"), None, T) is Prioridad.alta
    assert priority(Decimal("200000"), None, T) is Prioridad.media
    assert priority(Decimal("50000"), None, T) is Prioridad.baja


def test_priority_urgency_only_when_no_amount() -> None:
    # a missing amount routes by urgency alone — never defaulted to an amount
    assert priority(None, 100, T) is Prioridad.alta
    assert priority(None, 40, T) is Prioridad.media
    assert priority(None, 5, T) is Prioridad.baja
    assert priority(None, None, T) is Prioridad.baja


def test_build_accion_carries_rationale_and_none_amount() -> None:
    h = _h(monto=None, urgencia=20)
    a = build_accion(h, run_id="RUN1", t=T)
    assert a.estado is AccionEstado.propuesta
    assert a.monto_en_juego_ars is None
    assert a.mensaje_es == ""  # deterministic-only until narrate fills it
    assert '"tipo_accion": "x"' in a.rationale_json


def _h(monto=Decimal("100000"), urgencia=10, completitud=1.0, senial=1.0) -> Hallazgo:
    return Hallazgo(
        agente="t",
        tipo_accion="x",
        entidad_tipo="cliente",
        entidad_id="C1",
        monto_en_juego_ars=monto,
        urgencia_dias=urgencia,
        numeros={"k": "v"},
        completitud=completitud,
        senial=senial,
    )


# --- audit hash chain ----------------------------------------------------------


def test_audit_chain_records_and_verifies(repo) -> None:
    audit = AuditWriter(repo)
    audit.record("system", "run_started", "run", "RUN1", {"x": 1})
    audit.record("admin", "accion_aprobada", "accion", "ACC1", {"monto": "100"})
    events = repo.get_audit_events()
    assert len(events) == 2
    assert events[0].prev_hash is None
    assert events[1].prev_hash == events[0].hash
    assert verify_chain(events).ok


def test_audit_chain_detects_tampering(repo) -> None:
    audit = AuditWriter(repo)
    audit.record("system", "a", "run", "R", {"v": 1})
    audit.record("system", "b", "run", "R", {"v": 2})
    events = repo.get_audit_events()
    # tamper with the first event's detail
    tampered = [events[0].model_copy(update={"detalle_json": '{"v": 999}'}), events[1]]
    v = verify_chain(tampered)
    assert not v.ok and v.broken_at == 0


# --- maker-checker -------------------------------------------------------------


def test_resolve_approves_and_audits(repo) -> None:
    audit = AuditWriter(repo)
    accion = build_accion(_h(), run_id="RUN1", t=T)
    repo.insert_acciones([accion])

    resolved = resolve_accion(
        repo, audit, accion.accion_id, AccionEstado.aprobada, "admin", nota="OK"
    )
    assert resolved.estado is AccionEstado.aprobada
    assert resolved.resuelta_por == "admin"
    # resolution event + disabled-execution noop event, both audited and chained
    events = repo.get_audit_events()
    acciones = [e.accion for e in events]
    assert "accion_aprobada" in acciones
    assert "execution_noop_would_execute" in acciones
    assert verify_chain(events).ok


def test_resolve_edit_updates_message(repo) -> None:
    audit = AuditWriter(repo)
    accion = build_accion(_h(), run_id="RUN1", t=T)
    repo.insert_acciones([accion])
    resolved = resolve_accion(
        repo,
        audit,
        accion.accion_id,
        AccionEstado.editada,
        "admin",
        mensaje_editado="Texto editado",
    )
    assert resolved.estado is AccionEstado.editada
    assert resolved.mensaje_es == "Texto editado"


def test_double_resolution_fails_closed(repo) -> None:
    audit = AuditWriter(repo)
    accion = build_accion(_h(), run_id="RUN1", t=T)
    repo.insert_acciones([accion])
    resolve_accion(repo, audit, accion.accion_id, AccionEstado.aprobada, "admin")
    with pytest.raises(ReviewError, match="ya fue resuelta"):
        resolve_accion(repo, audit, accion.accion_id, AccionEstado.rechazada, "admin")


def test_resolve_unknown_action_fails_closed(repo) -> None:
    audit = AuditWriter(repo)
    with pytest.raises(ReviewError, match="no encontrada"):
        resolve_accion(repo, audit, "nope", AccionEstado.aprobada, "admin")


# --- PII -----------------------------------------------------------------------


def test_redact_drops_pii_columns() -> None:
    row = {
        "cliente_id": "C1",
        "nombre": "Juan",
        "documento": "20-1-2",
        "email": "a@b.com",
        "localidad": "Lomas",
    }
    out = redact("clientes", row)
    assert "documento" not in out and "email" not in out and "nombre" not in out
    assert out["cliente_id"] == "C1" and out["localidad"] == "Lomas"


def test_cliente_safe_context_has_no_pii() -> None:
    ctx = cliente_safe_context(f.cliente(cliente_id="C1", nombre="Juan Carlos Perez"))
    assert ctx["nombre"] == "Juan"  # first name only
    assert "documento" not in ctx and "email" not in ctx and "telefono" not in ctx
    assert "fecha_nacimiento" not in ctx
