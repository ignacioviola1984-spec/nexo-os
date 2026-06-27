"""Append-only, hash-chained audit log.

Each event's hash is computed over the previous event's hash plus the event's own
fields, so any tampering with an earlier row breaks every subsequent hash. This is
tamper-EVIDENCE, not tamper-prevention (see SECURITY.md): it lets you detect a break
in the underlying store, it does not physically prevent one. Application code only
ever appends — never updates or deletes.

Detail payloads carry identifiers only — never full PII.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from nexo_os.clock import now
from nexo_os.data.models import AuditEvent
from nexo_os.data.repository import NexoRepository


def _canonical_detail(detalle: dict) -> str:
    return json.dumps(detalle, sort_keys=True, ensure_ascii=False, default=str)


def compute_hash(
    *,
    prev_hash: str | None,
    evento_id: str,
    ts: datetime,
    actor: str,
    accion: str,
    entidad_tipo: str,
    entidad_id: str | None,
    detalle_json: str,
) -> str:
    payload = "|".join(
        [
            prev_hash or "",
            evento_id,
            ts.isoformat(),
            actor,
            accion,
            entidad_tipo,
            entidad_id or "",
            detalle_json,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditWriter:
    """Appends hash-chained events through the repository."""

    def __init__(self, repo: NexoRepository) -> None:
        self.repo = repo

    def record(
        self,
        actor: str,
        accion: str,
        entidad_tipo: str,
        entidad_id: str | None,
        detalle: dict | None = None,
        ts: datetime | None = None,
    ) -> AuditEvent:
        ts = ts or now()
        detalle_json = _canonical_detail(detalle or {})
        evento_id = uuid.uuid4().hex
        prev_hash = self.repo.get_last_audit_hash()
        h = compute_hash(
            prev_hash=prev_hash,
            evento_id=evento_id,
            ts=ts,
            actor=actor,
            accion=accion,
            entidad_tipo=entidad_tipo,
            entidad_id=entidad_id,
            detalle_json=detalle_json,
        )
        event = AuditEvent(
            evento_id=evento_id,
            ts=ts,
            actor=actor,
            accion=accion,
            entidad_tipo=entidad_tipo,
            entidad_id=entidad_id,
            detalle_json=detalle_json,
            prev_hash=prev_hash,
            hash=h,
        )
        self.repo.append_audit_event(event)
        return event


@dataclass(frozen=True)
class ChainVerification:
    ok: bool
    total: int
    broken_at: int | None  # index of the first event whose hash/link is invalid


def verify_chain(events: list[AuditEvent]) -> ChainVerification:
    """Recompute the chain and confirm each event links to the prior one."""
    prev_hash: str | None = None
    for i, e in enumerate(events):
        if e.prev_hash != prev_hash:
            return ChainVerification(ok=False, total=len(events), broken_at=i)
        expected = compute_hash(
            prev_hash=e.prev_hash,
            evento_id=e.evento_id,
            ts=e.ts,
            actor=e.actor,
            accion=e.accion,
            entidad_tipo=e.entidad_tipo,
            entidad_id=e.entidad_id,
            detalle_json=e.detalle_json,
        )
        if expected != e.hash:
            return ChainVerification(ok=False, total=len(events), broken_at=i)
        prev_hash = e.hash
    return ChainVerification(ok=True, total=len(events), broken_at=None)
