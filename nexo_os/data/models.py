"""Typed domain and system objects. Everything downstream reads these, never loose
dicts. Money fields are Decimal (exact). Field names match `schema_def.py`
column-for-column (enforced by a contract test).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --- Enums --------------------------------------------------------------------


class ClienteTipo(StrEnum):
    persona_fisica = "persona_fisica"
    persona_juridica = "persona_juridica"


class ClienteEstado(StrEnum):
    activo = "activo"
    inactivo = "inactivo"


class Ramo(StrEnum):
    auto = "auto"
    hogar = "hogar"
    vida = "vida"
    art = "art"
    caucion = "caucion"
    accidentes_personales = "accidentes_personales"
    comercio = "comercio"
    otros = "otros"


class PolizaEstado(StrEnum):
    vigente = "vigente"
    vencida = "vencida"
    anulada = "anulada"
    en_gestion = "en_gestion"
    renovada = "renovada"


class FrecuenciaPago(StrEnum):
    mensual = "mensual"
    trimestral = "trimestral"
    semestral = "semestral"
    anual = "anual"


class CuotaEstado(StrEnum):
    pendiente = "pendiente"
    pagada = "pagada"
    vencida = "vencida"
    parcial = "parcial"


class ComisionEstado(StrEnum):
    esperada = "esperada"
    liquidada = "liquidada"
    parcial = "parcial"
    con_diferencia = "con_diferencia"


class CanalOrigen(StrEnum):
    referido = "referido"
    web = "web"
    redes = "redes"
    llamado = "llamado"
    otro = "otro"


class LeadEstado(StrEnum):
    nuevo = "nuevo"
    contactado = "contactado"
    cotizado = "cotizado"
    presentado = "presentado"
    ganado = "ganado"
    perdido = "perdido"


class CotizacionEstado(StrEnum):
    emitida = "emitida"
    presentada = "presentada"
    aceptada = "aceptada"
    rechazada = "rechazada"
    vencida = "vencida"


class SiniestroEstado(StrEnum):
    abierto = "abierto"
    en_proceso = "en_proceso"
    pagado = "pagado"
    rechazado = "rechazado"
    cerrado = "cerrado"


class EntidadTipo(StrEnum):
    cliente = "cliente"
    lead = "lead"


class InteraccionTipo(StrEnum):
    llamado = "llamado"
    email = "email"
    visita = "visita"
    nota = "nota"


class Prioridad(StrEnum):
    alta = "alta"
    media = "media"
    baja = "baja"


class AccionEstado(StrEnum):
    propuesta = "propuesta"
    aprobada = "aprobada"
    rechazada = "rechazada"
    editada = "editada"
    vencida = "vencida"


class RunEstado(StrEnum):
    ok = "ok"
    con_warnings = "con_warnings"
    error = "error"


# --- Domain models ------------------------------------------------------------


class Cliente(_Base):
    cliente_id: str
    tipo: ClienteTipo
    nombre: str
    documento: str
    fecha_nacimiento: date | None
    email: str | None
    telefono: str | None
    localidad: str
    provincia: str
    segmento: str
    fecha_alta: date
    productor_id: str
    estado: ClienteEstado


class Poliza(_Base):
    poliza_id: str
    nro_poliza: str
    cliente_id: str
    aseguradora_id: str
    ramo: Ramo
    fecha_inicio_vigencia: date
    fecha_fin_vigencia: date
    prima_ars: Decimal
    suma_asegurada_ars: Decimal
    estado: PolizaEstado
    forma_pago: str
    frecuencia_pago: FrecuenciaPago
    comision_pct: Decimal
    productor_id: str
    poliza_origen_id: str | None


class Cuota(_Base):
    cuota_id: str
    poliza_id: str
    nro_cuota: int
    fecha_vencimiento: date
    monto_ars: Decimal
    estado: CuotaEstado
    fecha_pago: date | None
    monto_pagado_ars: Decimal


class Comision(_Base):
    comision_id: str
    poliza_id: str
    aseguradora_id: str
    periodo: str
    base_comisionable_ars: Decimal
    comision_pct: Decimal
    comision_esperada_ars: Decimal
    comision_liquidada_ars: Decimal | None
    fecha_liquidacion: date | None
    estado: ComisionEstado
    diferencia_ars: Decimal


class Lead(_Base):
    lead_id: str
    fecha_ingreso: date
    nombre_prospecto: str
    contacto: str
    canal_origen: CanalOrigen
    ramo: Ramo
    productor_id: str
    estado: LeadEstado
    fecha_ultimo_movimiento: date
    fecha_cierre: date | None
    motivo_perdida: str | None
    cliente_id: str | None


class Cotizacion(_Base):
    cotizacion_id: str
    lead_id: str
    aseguradora_id: str
    ramo: Ramo
    prima_cotizada_ars: Decimal
    fecha_cotizacion: date
    estado: CotizacionEstado
    vigencia_cotizacion: date | None
    poliza_id: str | None


class Siniestro(_Base):
    siniestro_id: str
    poliza_id: str
    fecha: date
    tipo: str
    monto_reclamado_ars: Decimal
    monto_pagado_ars: Decimal | None
    estado: SiniestroEstado


class Aseguradora(_Base):
    aseguradora_id: str
    nombre: str
    condiciones_comision_json: str  # JSON text; commission terms by ramo


class Productor(_Base):
    productor_id: str
    nombre: str
    equipo: str
    activo: bool


class Interaccion(_Base):
    interaccion_id: str
    entidad_tipo: EntidadTipo
    entidad_id: str
    fecha: date
    tipo: InteraccionTipo
    resumen: str


# --- System models ------------------------------------------------------------


class Accion(_Base):
    accion_id: str
    agente: str
    tipo_accion: str
    entidad_tipo: str
    entidad_id: str
    prioridad: Prioridad
    confianza: float
    monto_en_juego_ars: Decimal | None
    rationale_json: str
    mensaje_es: str
    estado: AccionEstado
    creada_en: datetime
    resuelta_en: datetime | None
    resuelta_por: str | None
    nota_revisor: str | None
    run_id: str


class AgentRun(_Base):
    run_id: str
    iniciado_en: datetime
    finalizado_en: datetime | None
    estado: RunEstado
    resumen_json: str
    data_source: str
    data_snapshot_fecha: date


class AuditEvent(_Base):
    evento_id: str
    ts: datetime
    actor: str
    accion: str
    entidad_tipo: str
    entidad_id: str | None
    detalle_json: str
    prev_hash: str | None
    hash: str


# Map model class -> table name (used by the repository and contract test).
MODEL_TABLE: dict[type[_Base], str] = {
    Cliente: "clientes",
    Poliza: "polizas",
    Cuota: "cuotas",
    Comision: "comisiones",
    Lead: "leads",
    Cotizacion: "cotizaciones",
    Siniestro: "siniestros",
    Aseguradora: "aseguradoras",
    Productor: "productores",
    Interaccion: "interacciones",
    Accion: "acciones",
    AgentRun: "agent_runs",
    AuditEvent: "audit_log",
}
