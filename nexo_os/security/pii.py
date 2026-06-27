"""PII minimization. The model and the logs receive only what a message needs —
never full documents, emails, phones, or birth dates. The PII registry comes from
the canonical schema (`schema_def.PII_FIELDS`), so flagging a field as PII there
automatically keeps it out of redacted views.
"""

from __future__ import annotations

from nexo_os.data.models import Cliente, Lead
from nexo_os.data.schema_def import PII_FIELDS


def first_name(nombre: str) -> str:
    """First token of a name only (never the full name in model/log context)."""
    return nombre.split()[0] if nombre else ""


def redact(table: str, row: dict) -> dict:
    """Drop every PII-flagged column for a table from a row dict."""
    pii = PII_FIELDS.get(table, set())
    return {k: v for k, v in row.items() if k not in pii}


def cliente_safe_context(cliente: Cliente) -> dict:
    """Non-PII context about a client, safe to send to the model / log.
    Identifies by id + first name only; no documento/email/telefono/birth date."""
    return {
        "cliente_id": cliente.cliente_id,
        "nombre": first_name(cliente.nombre),
        "localidad": cliente.localidad,
        "provincia": cliente.provincia,
        "segmento": cliente.segmento,
        "tipo": cliente.tipo.value,
    }


def lead_safe_context(lead: Lead) -> dict:
    """Non-PII context about a lead (no full prospect name / contact)."""
    return {
        "lead_id": lead.lead_id,
        "nombre": first_name(lead.nombre_prospecto),
        "canal_origen": lead.canal_origen.value,
        "ramo": lead.ramo.value,
        "estado": lead.estado.value,
    }
