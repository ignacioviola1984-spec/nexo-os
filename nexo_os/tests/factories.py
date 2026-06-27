"""Minimal typed-object builders for unit tests. Sensible defaults; override any field."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from nexo_os.data.models import (
    Cliente,
    Comision,
    Cotizacion,
    Cuota,
    Interaccion,
    Lead,
    Poliza,
    Siniestro,
)

SNAP = date(2026, 6, 30)


def cliente(cliente_id="C1", estado="activo", **o) -> Cliente:
    base = dict(
        cliente_id=cliente_id,
        tipo="persona_fisica",
        nombre="N",
        documento="20-99000001-0",
        fecha_nacimiento=date(1980, 1, 1),
        email="x@example.com",
        telefono="+54-11-40000000",
        localidad="Lomas",
        provincia="Buenos Aires",
        segmento="retail",
        fecha_alta=date(2020, 1, 1),
        productor_id="PRD-01",
        estado=estado,
    )
    return Cliente(**{**base, **o})


def poliza(
    poliza_id="POL1",
    cliente_id="C1",
    ramo="auto",
    estado="vigente",
    prima="100000.00",
    comision_pct="0.120000",
    fin=date(2026, 12, 31),
    **o,
) -> Poliza:
    base = dict(
        poliza_id=poliza_id,
        nro_poliza="N-1",
        cliente_id=cliente_id,
        aseguradora_id="ASEG-01",
        ramo=ramo,
        fecha_inicio_vigencia=date(2026, 1, 1),
        fecha_fin_vigencia=fin,
        prima_ars=Decimal(prima),
        suma_asegurada_ars=Decimal("1000000.00"),
        estado=estado,
        forma_pago="debito_automatico",
        frecuencia_pago="mensual",
        comision_pct=Decimal(comision_pct),
        productor_id="PRD-01",
        poliza_origen_id=None,
    )
    return Poliza(**{**base, **o})


def cuota(
    cuota_id="CUO1",
    poliza_id="POL1",
    estado="pendiente",
    venc=date(2026, 7, 15),
    monto="10000.00",
    pagado="0.00",
    fecha_pago=None,
    nro=1,
) -> Cuota:
    return Cuota(
        cuota_id=cuota_id,
        poliza_id=poliza_id,
        nro_cuota=nro,
        fecha_vencimiento=venc,
        monto_ars=Decimal(monto),
        estado=estado,
        fecha_pago=fecha_pago,
        monto_pagado_ars=Decimal(pagado),
    )


def comision(
    comision_id="COM1",
    poliza_id="POL1",
    periodo="2026-06",
    base="100000.00",
    pct="0.120000",
    esperada="12000.00",
    liquidada="12000.00",
    estado="liquidada",
    diferencia="0.00",
    fecha_liq=date(2026, 6, 20),
    **o,
) -> Comision:
    base_d = dict(
        comision_id=comision_id,
        poliza_id=poliza_id,
        aseguradora_id="ASEG-01",
        periodo=periodo,
        base_comisionable_ars=Decimal(base),
        comision_pct=Decimal(pct),
        comision_esperada_ars=Decimal(esperada),
        comision_liquidada_ars=None if liquidada is None else Decimal(liquidada),
        fecha_liquidacion=fecha_liq,
        estado=estado,
        diferencia_ars=Decimal(diferencia),
    )
    return Comision(**{**base_d, **o})


def lead(
    lead_id="L1",
    estado="nuevo",
    ramo="auto",
    canal="web",
    ingreso=date(2026, 6, 1),
    ultimo=date(2026, 6, 28),
    **o,
) -> Lead:
    base = dict(
        lead_id=lead_id,
        fecha_ingreso=ingreso,
        nombre_prospecto="P",
        contacto="p@example.com",
        canal_origen=canal,
        ramo=ramo,
        productor_id="PRD-01",
        estado=estado,
        fecha_ultimo_movimiento=ultimo,
        fecha_cierre=None,
        motivo_perdida=None,
        cliente_id=None,
    )
    return Lead(**{**base, **o})


def cotizacion(
    cotizacion_id="Q1",
    lead_id="L1",
    ramo="auto",
    estado="emitida",
    prima="100000.00",
    fecha=date(2026, 6, 1),
    poliza_id=None,
    **o,
) -> Cotizacion:
    base = dict(
        cotizacion_id=cotizacion_id,
        lead_id=lead_id,
        aseguradora_id="ASEG-01",
        ramo=ramo,
        prima_cotizada_ars=Decimal(prima),
        fecha_cotizacion=fecha,
        estado=estado,
        vigencia_cotizacion=None,
        poliza_id=poliza_id,
    )
    return Cotizacion(**{**base, **o})


def siniestro(
    siniestro_id="S1",
    poliza_id="POL1",
    estado="pagado",
    pagado="50000.00",
    reclamado="60000.00",
    fecha=date(2026, 3, 1),
) -> Siniestro:
    return Siniestro(
        siniestro_id=siniestro_id,
        poliza_id=poliza_id,
        fecha=fecha,
        tipo="x",
        monto_reclamado_ars=Decimal(reclamado),
        monto_pagado_ars=None if pagado is None else Decimal(pagado),
        estado=estado,
    )


def interaccion(
    interaccion_id="I1",
    entidad_id="C1",
    entidad_tipo="cliente",
    fecha=date(2026, 6, 1),
    tipo="llamado",
) -> Interaccion:
    return Interaccion(
        interaccion_id=interaccion_id,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        fecha=fecha,
        tipo=tipo,
        resumen="r",
    )
