"""Maker-checker. The agent is the maker (proposes); the broker is the checker, via
the inbox. An action is not 'done' until a human resolves it. Resolutions are
recorded immutably to the audit log. Approval records the decision; it does not send
anything (the execution seam is disabled - see security/execution.py).
"""

from __future__ import annotations

from nexo_os.audit import AuditWriter
from nexo_os.clock import now
from nexo_os.data.models import Accion, AccionEstado
from nexo_os.data.repository import NexoRepository
from nexo_os.enterprise.rbac import Permission, require
from nexo_os.security.execution import ExecutionAdapter, NoopExecutionAdapter

RESOLUTIONS = {AccionEstado.aprobada, AccionEstado.rechazada, AccionEstado.editada}


class ReviewError(RuntimeError):
    pass


def resolve_accion(
    repo: NexoRepository,
    audit: AuditWriter,
    accion_id: str,
    decision: AccionEstado,
    revisor: str,
    nota: str | None = None,
    mensaje_editado: str | None = None,
    execution: ExecutionAdapter | None = None,
    revisor_role: str | None = None,
) -> Accion:
    """Record a human decision on a proposed action. Fails closed on unknown action,
    already-resolved action, or an invalid decision.

    When ``revisor_role`` is provided, RBAC is enforced at this maker-checker boundary:
    a role without ``INBOX_RESOLVE`` (viewer, auditor) is refused even if the UI is
    bypassed. Passing None keeps the call backward-compatible for internal callers."""
    if revisor_role is not None:
        require(revisor_role, Permission.INBOX_RESOLVE)
    if decision not in RESOLUTIONS:
        raise ReviewError(f"Decisión inválida: {decision}")

    accion = repo.get_accion(accion_id)
    if accion is None:
        raise ReviewError(f"Acción no encontrada: {accion_id}")
    if accion.estado is not AccionEstado.propuesta:
        raise ReviewError(f"La acción {accion_id} ya fue resuelta ({accion.estado.value}).")

    resuelta_en = now()
    mensaje = mensaje_editado if decision is AccionEstado.editada else None
    repo.resolve_accion(
        accion_id,
        estado=decision,
        resuelta_en=resuelta_en,
        resuelta_por=revisor,
        nota_revisor=nota,
        mensaje_es=mensaje,
    )
    audit.record(
        actor=revisor,
        accion=f"accion_{decision.value}",
        entidad_tipo="accion",
        entidad_id=accion_id,
        detalle={
            "agente": accion.agente,
            "tipo_accion": accion.tipo_accion,
            "prioridad": accion.prioridad.value,
            "monto_en_juego_ars": (
                str(accion.monto_en_juego_ars) if accion.monto_en_juego_ars is not None else None
            ),
            "nota": nota,
        },
    )

    # disabled execution seam: approval records intent only, sends nothing
    if decision in (AccionEstado.aprobada, AccionEstado.editada):
        (execution or NoopExecutionAdapter(audit)).execute(accion, actor=revisor)

    resolved = repo.get_accion(accion_id)
    assert resolved is not None
    return resolved
