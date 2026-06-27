"""Execution seam — DISABLED in this build.

An approved action is recorded; it is NOT executed against any external system
(no email/WhatsApp/SMS, no AMS or insurer-portal write-back). This interface marks
the boundary for a future build. The only implementation, NoopExecutionAdapter,
records a "would execute" event to the audit log and sends nothing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from nexo_os.audit import AuditWriter
from nexo_os.data.models import Accion


class ExecutionAdapter(ABC):
    @abstractmethod
    def execute(self, accion: Accion, actor: str) -> None:
        """Carry out an approved action against an external system. (Future build.)"""


class NoopExecutionAdapter(ExecutionAdapter):
    """Records intent only. Wires nothing live."""

    def __init__(self, audit: AuditWriter) -> None:
        self.audit = audit

    def execute(self, accion: Accion, actor: str) -> None:
        self.audit.record(
            actor="system",
            accion="execution_noop_would_execute",
            entidad_tipo="accion",
            entidad_id=accion.accion_id,
            detalle={
                "tipo_accion": accion.tipo_accion,
                "agente": accion.agente,
                "nota": "Ejecución externa fuera de alcance en esta versión.",
                "aprobada_por": actor,
            },
        )
