"""Single source for all user-facing Spanish (rioplatense) copy. Keep UI strings
here, not scattered across the dashboard. Money is ARS unless stated otherwise.
"""

from __future__ import annotations

from decimal import Decimal

# --- App-level strings ---
APP_TITLE = "Nexo — Co-piloto de la corredora"
APP_SUBTITLE = "Análisis y acciones con números deterministas y aprobación humana"

# --- Navigation ---
NAV = {
    "overview": "Resumen ejecutivo",
    "inbox": "Bandeja de aprobaciones",
    "audit": "Auditoría",
}

# --- Generic ---
SIN_DATOS = "sin datos"
INSUFICIENTE = "datos insuficientes"
SNAPSHOT_LABEL = "Fecha de corte"
DATA_SOURCE_LABEL = "Fuente de datos"

# --- Action states ---
ESTADO_ACCION = {
    "propuesta": "Propuesta",
    "aprobada": "Aprobada",
    "rechazada": "Rechazada",
    "editada": "Editada",
    "vencida": "Vencida",
}

# --- Priority ---
PRIORIDAD = {"alta": "Alta", "media": "Media", "baja": "Baja"}

# --- Inbox controls ---
APROBAR = "Aprobar"
RECHAZAR = "Rechazar"
EDITAR = "Editar"
NOTA_REVISOR = "Nota del revisor (opcional)"
APROBACION_NO_ENVIA = (
    "La aprobación registra la decisión de forma inmutable. No envía ni ejecuta "
    "nada hacia sistemas externos en esta versión."
)

# --- Agent display names (Spanish), keyed by agent id ---
AGENTES = {
    "cartera": "Cartera",
    "cobranza": "Cobranza",
    "morosidad": "Morosidad",
    "renewals": "Renovaciones",
    "retention": "Retención de ingresos",
    "conversion": "Conversión",
    "pipeline": "Pipeline",
    "leads_control": "Control de leads/cotizaciones",
    "profitability": "Rentabilidad por producto/cartera",
    "comisiones": "Seguimiento de comisiones",
}


def fmt_ars(amount: Decimal | int | float | None) -> str:
    """Format an ARS amount for display, or the 'sin datos' state when None.

    Uses Argentine convention: thousands '.', decimals ','. Never invents a value.
    """
    if amount is None:
        return SIN_DATOS
    q = Decimal(amount).quantize(Decimal("0.01"))
    sign = "-" if q < 0 else ""
    entero, _, dec = f"{abs(q):.2f}".partition(".")
    miles = ".".join(_chunks(entero))
    return f"{sign}$ {miles},{dec}"


def fmt_pct(fraction: float | Decimal | None, decimals: int = 1) -> str:
    if fraction is None:
        return SIN_DATOS
    return f"{float(fraction) * 100:.{decimals}f}%".replace(".", ",")


def _chunks(entero: str) -> list[str]:
    rev = entero[::-1]
    parts = [rev[i : i + 3][::-1] for i in range(0, len(rev), 3)]
    return parts[::-1]
