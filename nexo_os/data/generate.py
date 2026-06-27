"""Synthetic data generator for a single Argentine PyME insurance brokerage.

Produces a realistic book conforming exactly to the canonical schema, and plants
detectable situations whose EXACT ground truth (counts, IDs, and expected figures)
is recorded in `ground_truth.json` + `GROUND_TRUTH.md`. The ground-truth figures are
accumulated from the actual constructed rows here — an implementation path entirely
independent of `nexo_os.core` — so the evals (Phase 8) catch a bug in either side.

Design choices that keep the ground truth EXACT:
  * The healthy baseline deliberately avoids triggering any detector (no overdue
    installments, no near-term expiries, no commission discrepancies, etc.).
  * Each anomaly is planted in a dedicated cluster with distinctive IDs.
  * Reconciliation ties hold by construction (current-period commission rows mirror
    in-force policy premium x pct).

Deterministic: a fixed seed makes every run reproducible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb

from nexo_os.config import get_settings
from nexo_os.data.schema_def import DOMAIN_TABLES, TABLES_BY_NAME, render_duckdb_ddl
from nexo_os.logging_setup import configure_logging, get_logger
from nexo_os.rng import DeterministicRng

log = get_logger("generate")

# --- domain constants ---------------------------------------------------------

LOCALIDADES = [
    "Lomas de Zamora",
    "Banfield",
    "Lanús",
    "Avellaneda",
    "Quilmes",
    "Adrogué",
    "Temperley",
    "Wilde",
    "Berazategui",
    "Florencio Varela",
]
PROVINCIA = "Buenos Aires"
SEGMENTOS = ["retail", "pyme", "premium"]
FORMAS_PAGO = ["debito_automatico", "tarjeta", "transferencia", "efectivo"]
EQUIPOS = ["Equipo Norte", "Equipo Sur"]

# commission fraction by ramo (0.12 = 12%)
COMISION_POR_RAMO: dict[str, Decimal] = {
    "auto": Decimal("0.120000"),
    "hogar": Decimal("0.150000"),
    "vida": Decimal("0.200000"),
    "art": Decimal("0.080000"),
    "caucion": Decimal("0.100000"),
    "accidentes_personales": Decimal("0.180000"),
    "comercio": Decimal("0.140000"),
    "otros": Decimal("0.100000"),
}
# annual premium range (ARS) by ramo, plausible 2026 magnitudes
PRIMA_RANGO: dict[str, tuple[int, int]] = {
    "auto": (200_000, 900_000),
    "hogar": (80_000, 320_000),
    "vida": (150_000, 600_000),
    "art": (300_000, 2_000_000),
    "caucion": (120_000, 500_000),
    "accidentes_personales": (60_000, 200_000),
    "comercio": (250_000, 1_500_000),
    "otros": (100_000, 400_000),
}
# baseline ramo mix (caucion is reserved for the controlled loss-ratio scenario)
RAMO_MIX = [
    ("auto", 0.40),
    ("hogar", 0.25),
    ("vida", 0.08),
    ("art", 0.08),
    ("comercio", 0.07),
    ("accidentes_personales", 0.06),
    ("otros", 0.06),
]
FREQ_INSTALLMENTS = {"mensual": 12, "trimestral": 4, "semestral": 2, "anual": 1}
FREQ_MIX = [("mensual", 0.5), ("trimestral", 0.2), ("semestral", 0.15), ("anual", 0.15)]


def q2(x: Decimal | int | float | str) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"))


def period_of(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    return date(y, m % 12 + 1, min(d.day, 28))


@dataclass
class Builder:
    seed: int
    snapshot: date
    rng: DeterministicRng = field(init=False)
    tables: dict[str, list[dict]] = field(
        default_factory=lambda: {t.name: [] for t in DOMAIN_TABLES}
    )
    gt: dict = field(default_factory=dict)
    _seq: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.rng = DeterministicRng(self.seed)
        self.aseguradoras: list[str] = []
        self.productores: list[str] = []

    # --- id helpers -----------------------------------------------------------

    def _id(self, prefix: str) -> str:
        n = self._seq.get(prefix, 0) + 1
        self._seq[prefix] = n
        return f"{prefix}-{n:05d}"

    def add(self, table: str, **row: object) -> dict:
        self.tables[table].append(row)
        return row

    # --- reference data -------------------------------------------------------

    def build_reference(self) -> None:
        for i in range(1, 6):
            aid = f"ASEG-{i:02d}"
            self.aseguradoras.append(aid)
            terms = {ramo: str(pct) for ramo, pct in COMISION_POR_RAMO.items()}
            self.add(
                "aseguradoras",
                aseguradora_id=aid,
                nombre=f"Aseguradora {i}",
                condiciones_comision_json=json.dumps(terms),
            )
        for i in range(1, 7):
            pid = f"PRD-{i:02d}"
            self.productores.append(pid)
            self.add(
                "productores",
                productor_id=pid,
                nombre=f"Productor {i}",
                equipo=EQUIPOS[i % len(EQUIPOS)],
                activo=True,
            )

    # --- clients --------------------------------------------------------------

    def _new_cliente(self, cid: str, estado: str = "activo", tipo: str = "persona_fisica") -> dict:
        n = self._seq.get("_cli_pii", 0) + 1
        self._seq["_cli_pii"] = n
        # synthetic PII: reserved/invalid document range, @example.com, obviously fake
        documento = f"20-99{n:06d}-0"  # 99xxxxxx is not a valid CUIT range
        return self.add(
            "clientes",
            cliente_id=cid,
            tipo=tipo,
            nombre=f"Cliente Sintético {n}",
            documento=documento,
            fecha_nacimiento=date(1960, 1, 1) + timedelta(days=self.rng.randint(0, 16000)),
            email=f"cliente{n}@example.com",
            telefono=f"+54-11-4{n:07d}",
            localidad=self.rng.choice(LOCALIDADES),
            provincia=PROVINCIA,
            segmento=self.rng.choice(SEGMENTOS),
            fecha_alta=self.snapshot - timedelta(days=self.rng.randint(120, 2200)),
            productor_id=self.rng.choice(self.productores),
            estado=estado,
        )

    # --- policies + installments + current-period commission ------------------

    def _new_poliza(
        self,
        cliente_id: str,
        ramo: str,
        *,
        fin_offset_days: int,
        estado: str = "vigente",
        poliza_id: str | None = None,
        prima: Decimal | None = None,
        poliza_origen_id: str | None = None,
    ) -> dict:
        pid = poliza_id or self._id("POL")
        lo, hi = PRIMA_RANGO[ramo]
        prima = prima if prima is not None else q2(self.rng.randint(lo, hi))
        fin = self.snapshot + timedelta(days=fin_offset_days)
        inicio = fin - timedelta(days=365)
        pct = COMISION_POR_RAMO[ramo]
        freq = self.rng.weighted(FREQ_MIX)
        return self.add(
            "polizas",
            poliza_id=pid,
            nro_poliza=f"{ramo[:3].upper()}-{pid[-5:]}",
            cliente_id=cliente_id,
            aseguradora_id=self.rng.choice(self.aseguradoras),
            ramo=ramo,
            fecha_inicio_vigencia=inicio,
            fecha_fin_vigencia=fin,
            prima_ars=prima,
            suma_asegurada_ars=q2(prima * self.rng.randint(20, 80)),
            estado=estado,
            forma_pago=self.rng.choice(FORMAS_PAGO),
            frecuencia_pago=freq,
            comision_pct=pct,
            productor_id=self.rng.choice(self.productores),
            poliza_origen_id=poliza_origen_id,
        )

    def _installments(self, pol: dict, *, all_paid: bool = True) -> list[dict]:
        """Build a healthy payment plan: past installments paid, future pending."""
        freq = pol["frecuencia_pago"]
        n = FREQ_INSTALLMENTS[freq]
        step = 12 // n
        monto = q2(pol["prima_ars"] / n)
        rows = []
        for k in range(n):
            venc = add_months(pol["fecha_inicio_vigencia"], k * step)
            if venc <= self.snapshot:
                estado, pagado, fpago = (
                    "pagada",
                    monto,
                    venc + timedelta(days=self.rng.randint(0, 5)),
                )
            else:
                estado, pagado, fpago = "pendiente", q2(0), None
            rows.append(
                self.add(
                    "cuotas",
                    cuota_id=self._id("CUO"),
                    poliza_id=pol["poliza_id"],
                    nro_cuota=k + 1,
                    fecha_vencimiento=venc,
                    monto_ars=monto,
                    estado=estado,
                    fecha_pago=fpago,
                    monto_pagado_ars=pagado,
                )
            )
        return rows

    def _current_commission(self, pol: dict) -> None:
        """One clean current-period commission row per in-force policy (ties to cartera)."""
        base = pol["prima_ars"]
        esperada = q2(base * pol["comision_pct"])
        self.add(
            "comisiones",
            comision_id=self._id("COM"),
            poliza_id=pol["poliza_id"],
            aseguradora_id=pol["aseguradora_id"],
            periodo=period_of(self.snapshot),
            base_comisionable_ars=base,
            comision_pct=pol["comision_pct"],
            comision_esperada_ars=esperada,
            comision_liquidada_ars=esperada,
            fecha_liquidacion=self.snapshot - timedelta(days=self.rng.randint(1, 20)),
            estado="liquidada",
            diferencia_ars=q2(0),
        )

    def _register_inforce(self, pol: dict) -> None:
        """Every vigente policy contributes to cartera totals and gets a clean
        current-period commission row (keeps cartera<->comisiones reconciliation exact)."""
        self._current_commission(pol)
        c = self.gt["cartera"]
        c["polizas_vigentes"] += 1
        c["prima_total_ars"] += pol["prima_ars"]
        c["comision_esperada_ars"] += q2(pol["prima_ars"] * pol["comision_pct"])

    def _interaccion(self, entidad_tipo: str, entidad_id: str, dias_atras: int) -> None:
        self.add(
            "interacciones",
            interaccion_id=self._id("INT"),
            entidad_tipo=entidad_tipo,
            entidad_id=entidad_id,
            fecha=self.snapshot - timedelta(days=dias_atras),
            tipo=self.rng.choice(["llamado", "email", "visita", "nota"]),
            resumen="Contacto de seguimiento.",
        )

    # --- baseline (healthy: triggers no detector) -----------------------------

    def build_baseline(self, n_clientes: int) -> None:
        self.gt["cartera"] = {
            "polizas_vigentes": 0,
            "prima_total_ars": q2(0),
            "comision_esperada_ars": q2(0),
        }
        for _ in range(n_clientes):
            cid = self._id("CLI")
            self._new_cliente(cid, estado="activo")
            self._interaccion("cliente", cid, dias_atras=self.rng.randint(1, 120))
            for _ in range(self.rng.randint(1, 4)):
                ramo = self.rng.weighted(RAMO_MIX)
                pol = self._new_poliza(cid, ramo, fin_offset_days=self.rng.randint(100, 360))
                self._installments(pol)
                self._register_inforce(pol)

    # --- planted: morosidad / cobranza ----------------------------------------

    def plant_morosidad(self) -> None:
        plan = {"1-30": (5, 5, 30), "31-60": (4, 31, 60), "61-90": (3, 61, 90), "90+": (3, 95, 160)}
        buckets: dict[str, dict] = {}
        ids: list[str] = []
        clientes_90plus: list[str] = []
        for label, (count, dlo, dhi) in plan.items():
            b_count, b_ars = 0, q2(0)
            for _ in range(count):
                cid = self._id("CLI")
                self._new_cliente(cid, estado="activo")
                self._interaccion("cliente", cid, dias_atras=self.rng.randint(1, 60))
                ramo = self.rng.weighted(RAMO_MIX)
                pol = self._new_poliza(cid, ramo, fin_offset_days=self.rng.randint(120, 360))
                self._register_inforce(pol)
                dias = self.rng.randint(dlo, dhi)
                monto = q2(self.rng.randint(40_000, 250_000))
                cuo_id = self._id("CUO")
                self.add(
                    "cuotas",
                    cuota_id=cuo_id,
                    poliza_id=pol["poliza_id"],
                    nro_cuota=1,
                    fecha_vencimiento=self.snapshot - timedelta(days=dias),
                    monto_ars=monto,
                    estado="vencida",
                    fecha_pago=None,
                    monto_pagado_ars=q2(0),
                )
                b_count += 1
                b_ars += monto
                ids.append(cuo_id)
                if label == "90+":
                    clientes_90plus.append(cid)
            buckets[label] = {"count": b_count, "ars": b_ars}
        total_ars = sum((b["ars"] for b in buckets.values()), q2(0))
        total_count = sum(b["count"] for b in buckets.values())
        self.gt["morosidad"] = {
            "buckets": buckets,
            "total_vencido_ars": total_ars,
            "total_count": total_count,
            "cuota_ids": ids,
        }
        # cobranza acts on the same overdue universe -> totals reconcile
        self.gt["cobranza"] = {"total_recuperable_ars": total_ars, "items_count": total_count}
        self._clientes_lapse = clientes_90plus

    # --- planted: renewals -----------------------------------------------------

    def plant_renewals(self) -> None:
        windows = {"30": (4, 5, 30), "60": (3, 31, 60), "90": (2, 61, 90)}
        by_window: dict[str, list[str]] = {}
        prima_en_riesgo = q2(0)
        at_risk_ids: list[str] = []
        at_risk_prima = q2(0)
        for w, (count, dlo, dhi) in windows.items():
            ids: list[str] = []
            for i in range(count):
                cid = self._id("CLI")
                self._new_cliente(cid, estado="activo")
                self._interaccion("cliente", cid, dias_atras=self.rng.randint(1, 90))
                ramo = self.rng.weighted(RAMO_MIX)
                pol = self._new_poliza(cid, ramo, fin_offset_days=self.rng.randint(dlo, dhi))
                self._installments(pol)
                self._register_inforce(pol)
                ids.append(pol["poliza_id"])
                prima_en_riesgo += pol["prima_ars"]
                # mark the first policy of each window as at-risk: add a paid claim
                if i == 0:
                    at_risk_ids.append(pol["poliza_id"])
                    at_risk_prima += pol["prima_ars"]
                    self.add(
                        "siniestros",
                        siniestro_id=self._id("SIN"),
                        poliza_id=pol["poliza_id"],
                        fecha=self.snapshot - timedelta(days=self.rng.randint(30, 200)),
                        tipo="siniestro_menor",
                        monto_reclamado_ars=q2(self.rng.randint(50_000, 150_000)),
                        monto_pagado_ars=q2(self.rng.randint(20_000, 90_000)),
                        estado="pagado",
                    )
            by_window[w] = ids
        self.gt["renewals"] = {
            "expira_30_ids": by_window["30"],
            "expira_60_ids": by_window["60"],
            "expira_90_ids": by_window["90"],
            "expira_30_count": len(by_window["30"]),
            "expira_60_count": len(by_window["60"]),
            "expira_90_count": len(by_window["90"]),
            "expira_total_90d_count": sum(len(v) for v in by_window.values()),
            "prima_en_riesgo_90d_ars": prima_en_riesgo,
            "at_risk_ids": at_risk_ids,
            "at_risk_prima_ars": at_risk_prima,
        }

    # --- planted: commission tracking -----------------------------------------

    def plant_comisiones(self) -> None:
        # (a) discrepancies: settled < expected, estado con_diferencia, prior period
        disc_ids: list[str] = []
        total_dif = q2(0)
        for _ in range(6):
            cid = self._id("CLI")
            self._new_cliente(cid, estado="activo")
            self._interaccion("cliente", cid, dias_atras=self.rng.randint(1, 90))
            ramo = self.rng.weighted(RAMO_MIX)
            pol = self._new_poliza(cid, ramo, fin_offset_days=self.rng.randint(120, 360))
            self._installments(pol)
            self._register_inforce(pol)
            base = pol["prima_ars"]
            esperada = q2(base * pol["comision_pct"])
            liquidada = q2(esperada * Decimal("0.7"))
            dif = q2(esperada - liquidada)
            com_id = self._id("COM")
            self.add(
                "comisiones",
                comision_id=com_id,
                poliza_id=pol["poliza_id"],
                aseguradora_id=pol["aseguradora_id"],
                periodo=period_of(add_months(self.snapshot, -1)),
                base_comisionable_ars=base,
                comision_pct=pol["comision_pct"],
                comision_esperada_ars=esperada,
                comision_liquidada_ars=liquidada,
                fecha_liquidacion=self.snapshot - timedelta(days=self.rng.randint(20, 40)),
                estado="con_diferencia",
                diferencia_ars=dif,
            )
            disc_ids.append(com_id)
            total_dif += dif
        # (b) aged receivable: esperada, unliquidated, period older than overdue window
        recv_ids: list[str] = []
        total_recv = q2(0)
        aged_period = period_of(add_months(self.snapshot, -2))  # ~60+ days old
        for _ in range(4):
            cid = self._id("CLI")
            self._new_cliente(cid, estado="activo")
            self._interaccion("cliente", cid, dias_atras=self.rng.randint(1, 90))
            ramo = self.rng.weighted(RAMO_MIX)
            pol = self._new_poliza(cid, ramo, fin_offset_days=self.rng.randint(120, 360))
            self._installments(pol)
            self._register_inforce(pol)
            base = pol["prima_ars"]
            esperada = q2(base * pol["comision_pct"])
            com_id = self._id("COM")
            self.add(
                "comisiones",
                comision_id=com_id,
                poliza_id=pol["poliza_id"],
                aseguradora_id=pol["aseguradora_id"],
                periodo=aged_period,
                base_comisionable_ars=base,
                comision_pct=pol["comision_pct"],
                comision_esperada_ars=esperada,
                comision_liquidada_ars=None,
                fecha_liquidacion=None,
                estado="esperada",
                diferencia_ars=esperada,
            )
            recv_ids.append(com_id)
            total_recv += esperada
        self.gt["comisiones"] = {
            "discrepancia_ids": disc_ids,
            "total_diferencia_ars": total_dif,
            "receivable_aged_ids": recv_ids,
            "receivable_aged_ars": total_recv,
            "aged_period": aged_period,
        }

    # --- planted: lead/quote control + conversion + pipeline ------------------

    def plant_leads_and_pipeline(self, n_baseline_leads: int) -> None:
        won = lost = 0
        bound = quotes_total = 0
        open_value = q2(0)
        # healthy baseline leads with recent movement
        for _ in range(n_baseline_leads):
            lid = self._id("LEAD")
            estado = self.rng.weighted(
                [
                    ("ganado", 0.2),
                    ("perdido", 0.3),
                    ("presentado", 0.2),
                    ("cotizado", 0.15),
                    ("contactado", 0.1),
                    ("nuevo", 0.05),
                ]
            )
            ramo = self.rng.weighted(RAMO_MIX)
            ingreso = self.snapshot - timedelta(days=self.rng.randint(10, 120))
            self.add(
                "leads",
                lead_id=lid,
                fecha_ingreso=ingreso,
                nombre_prospecto=f"Prospecto {lid[-5:]}",
                contacto=f"prospecto{lid[-5:]}@example.com",
                canal_origen=self.rng.choice(["referido", "web", "redes", "llamado", "otro"]),
                ramo=ramo,
                productor_id=self.rng.choice(self.productores),
                estado=estado,
                fecha_ultimo_movimiento=self.snapshot - timedelta(days=self.rng.randint(0, 4)),
                fecha_cierre=(
                    (self.snapshot - timedelta(days=self.rng.randint(0, 5)))
                    if estado in ("ganado", "perdido")
                    else None
                ),
                motivo_perdida="precio" if estado == "perdido" else None,
                cliente_id=None,
            )
            if estado == "ganado":
                won += 1
            elif estado == "perdido":
                lost += 1
            # quotes for cotizado+
            if estado in ("cotizado", "presentado", "ganado", "perdido"):
                quotes_total += 1
                prima = q2(self.rng.randint(*PRIMA_RANGO[ramo]))
                q_estado = {
                    "cotizado": "emitida",
                    "presentado": "presentada",
                    "ganado": "aceptada",
                    "perdido": "rechazada",
                }[estado]
                bound_pol = None
                if estado == "ganado":
                    bound += 1
                    bound_pol = f"POLBIND-{lid[-5:]}"
                self.add(
                    "cotizaciones",
                    cotizacion_id=self._id("COT"),
                    lead_id=lid,
                    aseguradora_id=self.rng.choice(self.aseguradoras),
                    ramo=ramo,
                    prima_cotizada_ars=prima,
                    fecha_cotizacion=ingreso + timedelta(days=2),
                    estado=q_estado,
                    vigencia_cotizacion=None,
                    poliza_id=bound_pol,
                )
                if estado in ("cotizado", "presentado"):
                    open_value += prima
        # planted: leads stuck past SLA (open, no movement for a long time)
        sla_ids: list[str] = []
        for _ in range(7):
            lid = self._id("LEAD")
            self.add(
                "leads",
                lead_id=lid,
                fecha_ingreso=self.snapshot - timedelta(days=self.rng.randint(40, 90)),
                nombre_prospecto=f"Prospecto Estancado {lid[-5:]}",
                contacto=f"estancado{lid[-5:]}@example.com",
                canal_origen="web",
                ramo=self.rng.weighted(RAMO_MIX),
                productor_id=self.rng.choice(self.productores),
                estado=self.rng.choice(["nuevo", "contactado"]),
                fecha_ultimo_movimiento=self.snapshot - timedelta(days=self.rng.randint(15, 40)),
                fecha_cierre=None,
                motivo_perdida=None,
                cliente_id=None,
            )
            sla_ids.append(lid)
        # planted: quotes issued but never presented (emitida, stale)
        np_ids: list[str] = []
        for _ in range(5):
            lid = self._id("LEAD")
            ramo = self.rng.weighted(RAMO_MIX)
            self.add(
                "leads",
                lead_id=lid,
                fecha_ingreso=self.snapshot - timedelta(days=self.rng.randint(20, 60)),
                nombre_prospecto=f"Prospecto Cotizado {lid[-5:]}",
                contacto=f"cot{lid[-5:]}@example.com",
                canal_origen="referido",
                ramo=ramo,
                productor_id=self.rng.choice(self.productores),
                estado="cotizado",
                fecha_ultimo_movimiento=self.snapshot - timedelta(days=self.rng.randint(15, 30)),
                fecha_cierre=None,
                motivo_perdida=None,
                cliente_id=None,
            )
            cot_id = self._id("COT")
            self.add(
                "cotizaciones",
                cotizacion_id=cot_id,
                lead_id=lid,
                aseguradora_id=self.rng.choice(self.aseguradoras),
                ramo=ramo,
                prima_cotizada_ars=q2(self.rng.randint(*PRIMA_RANGO[ramo])),
                fecha_cotizacion=self.snapshot - timedelta(days=self.rng.randint(15, 30)),
                estado="emitida",
                vigencia_cotizacion=None,
                poliza_id=None,
            )
            np_ids.append(cot_id)
        self.gt["leads_control"] = {
            "sla_breach_ids": sla_ids,
            "sla_breach_count": len(sla_ids),
            "quotes_no_presentadas_ids": np_ids,
            "quotes_no_presentadas_count": len(np_ids),
        }
        self.gt["conversion"] = {
            "leads_ganados": won,
            "leads_perdidos": lost,
            "leads_cerrados": won + lost,
            "quotes_bound": bound,
            "quotes_total_cerradas": quotes_total,
        }
        self.gt["pipeline"] = {"open_value_ars": open_value}

    # --- planted: inactive clients with no in-force policy --------------------

    def plant_inactivos(self) -> None:
        ids: list[str] = []
        for _ in range(8):
            cid = self._id("CLI")
            self._new_cliente(cid, estado="inactivo")
            # an old, anulada policy (not in force) — does not touch cartera
            pol = self._new_poliza(
                cid, "auto", fin_offset_days=-self.rng.randint(40, 200), estado="anulada"
            )
            _ = pol
            ids.append(cid)
        self.gt["inactivos_sin_poliza_ids"] = ids
        self.gt["inactivos_sin_poliza_count"] = len(ids)

    # --- planted: caucion controlled loss ratio (profitability) ---------------

    def plant_profitability(self) -> None:
        premium_total = q2(0)
        claims_paid_total = q2(0)
        for i in range(6):
            cid = self._id("CLI")
            self._new_cliente(cid, estado="activo")
            self._interaccion("cliente", cid, dias_atras=self.rng.randint(1, 90))
            prima = q2(self.rng.randint(*PRIMA_RANGO["caucion"]))
            pol = self._new_poliza(
                cid, "caucion", fin_offset_days=self.rng.randint(120, 360), prima=prima
            )
            self._installments(pol)
            self._register_inforce(pol)
            premium_total += prima
            # paid claims sized so the ramo loss ratio lands ~0.85 (> alert)
            paid = q2(prima * Decimal("0.85"))
            claims_paid_total += paid
            self.add(
                "siniestros",
                siniestro_id=self._id("SIN"),
                poliza_id=pol["poliza_id"],
                fecha=self.snapshot - timedelta(days=self.rng.randint(20, 250)),
                tipo="ejecucion_caucion",
                monto_reclamado_ars=q2(paid * Decimal("1.1")),
                monto_pagado_ars=paid,
                estado="pagado",
            )
            _ = i
        loss_ratio = (claims_paid_total / premium_total) if premium_total else Decimal("0")
        self.gt["profitability"] = {
            "ramo": "caucion",
            "caucion_premium_ars": premium_total,
            "caucion_claims_paid_ars": claims_paid_total,
            "caucion_loss_ratio": loss_ratio,
            "unprofitable_ramos": ["caucion"],
        }

    # --- planted: retention (commission at risk) ------------------------------

    def plant_retention(self) -> None:
        """At-risk clients: long inactivity AND in-force policy. Commission at risk =
        sum of current-period expected commission over their vigente policies."""
        ids: list[str] = []
        total_at_risk = q2(0)
        per_client: dict[str, str] = {}
        for _ in range(5):
            cid = self._id("CLI")
            self._new_cliente(cid, estado="activo")
            # stale interaction -> inactivity churn signal (> inactivity_days)
            self._interaccion("cliente", cid, dias_atras=self.rng.randint(200, 400))
            ramo = self.rng.weighted(RAMO_MIX)
            pol = self._new_poliza(cid, ramo, fin_offset_days=self.rng.randint(120, 360))
            self._installments(pol)
            self._register_inforce(pol)
            at_risk = q2(pol["prima_ars"] * pol["comision_pct"])
            ids.append(cid)
            per_client[cid] = str(at_risk)
            total_at_risk += at_risk
        top_client = max(per_client, key=lambda k: Decimal(per_client[k]))
        self.gt["retention"] = {
            "at_risk_client_ids": ids,
            "at_risk_count": len(ids),
            "comision_en_riesgo_ars": total_at_risk,
            "per_client_ars": per_client,
            "top_client_id": top_client,
        }

    # --- orchestration --------------------------------------------------------

    def build(self) -> None:
        self.build_reference()
        self.build_baseline(n_clientes=300)
        self.plant_morosidad()
        self.plant_renewals()
        self.plant_comisiones()
        self.plant_leads_and_pipeline(n_baseline_leads=200)
        self.plant_inactivos()
        self.plant_profitability()
        self.plant_retention()
        self._finalize_gt()

    def _finalize_gt(self) -> None:
        self.gt["snapshot_fecha"] = self.snapshot.isoformat()
        self.gt["seed"] = self.seed
        self.gt["counts"] = {t: len(rows) for t, rows in self.tables.items()}
        # stringify cartera decimals
        c = self.gt["cartera"]
        c["prima_total_ars"] = str(c["prima_total_ars"])
        c["comision_esperada_ars"] = str(c["comision_esperada_ars"])


def _to_jsonable(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_jsonable(v) for v in obj]
    return obj


def _row_to_tuple(table: str, row: dict) -> list:
    cols = [c.name for c in TABLES_BY_NAME[table].columns]
    return [row[c] for c in cols]


def generate(seed: int, snapshot: date) -> Builder:
    b = Builder(seed=seed, snapshot=snapshot)
    b.build()
    return b


def generate_and_load() -> Builder:
    """Generate the synthetic dataset, write it to the DuckDB store, and emit the
    ground-truth files. Reproducible for a fixed seed."""
    configure_logging()
    settings = get_settings()
    seed = settings.synthetic_seed
    snapshot = settings.synthetic_snapshot_fecha
    b = generate(seed, snapshot)

    db_path = settings.synthetic_db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    con.execute(render_duckdb_ddl())
    for table in (t.name for t in DOMAIN_TABLES):
        rows = b.tables[table]
        if not rows:
            continue
        cols = [c.name for c in TABLES_BY_NAME[table].columns]
        placeholders = ", ".join("?" for _ in cols)
        con.executemany(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
            [_row_to_tuple(table, r) for r in rows],
        )
    con.close()

    # ground-truth files live next to the synthetic store
    gt_dir = db_path.parent
    (gt_dir / "ground_truth.json").write_text(
        json.dumps(_to_jsonable(b.gt), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _write_ground_truth_md(gt_dir / "GROUND_TRUTH.md", b)
    log.info(
        "seed.complete",
        counts=b.gt["counts"],
        snapshot=snapshot.isoformat(),
        store=str(db_path),
    )
    return b


def _write_ground_truth_md(path: Path, b: Builder) -> None:
    gt = b.gt
    m = gt["morosidad"]
    lines = [
        "# Synthetic ground truth",
        "",
        "> GENERATED by `nexo_os/data/generate.py` (do not edit by hand). These are the",
        "> EXACT planted facts the evals assert against. Figures here are accumulated from",
        "> the constructed rows — an implementation path independent of `nexo_os.core`.",
        "",
        f"- Seed: `{gt['seed']}`",
        f"- Snapshot date: `{gt['snapshot_fecha']}`",
        "- Synthetic PII is visibly non-real (reserved `20-99xxxxxx-0` documents, "
        "`@example.com` emails, obviously fake names).",
        "",
        "## Row counts",
        "",
        "| Table | Rows |",
        "|---|---|",
    ]
    lines += [f"| `{t}` | {n} |" for t, n in gt["counts"].items()]
    lines += [
        "",
        "## Cartera (in force)",
        "",
        f"- Vigentes: **{gt['cartera']['polizas_vigentes']}**",
        f"- Prima total: **ARS {gt['cartera']['prima_total_ars']}**",
        f"- Comisión esperada (período actual): **ARS {gt['cartera']['comision_esperada_ars']}**",
        "",
        "## Morosidad / Cobranza (reconcile on the same overdue universe)",
        "",
        f"- Total vencido: **ARS {m['total_vencido_ars']}** across **{m['total_count']}** "
        "installments.",
        "",
        "| Bucket | Count | ARS |",
        "|---|---|---|",
    ]
    for label, b_ in m["buckets"].items():
        lines.append(f"| {label} | {b_['count']} | {b_['ars']} |")
    r = gt["renewals"]
    lines += [
        "",
        "## Renovaciones",
        "",
        f"- Expiran ≤30d: **{r['expira_30_count']}**, 31-60d: **{r['expira_60_count']}**, "
        f"61-90d: **{r['expira_90_count']}** (total ≤90d: **{r['expira_total_90d_count']}**).",
        f"- Prima en riesgo (≤90d): **ARS {r['prima_en_riesgo_90d_ars']}**.",
        f"- At-risk renewals (claim history): **{len(r['at_risk_ids'])}** policies, "
        f"prima **ARS {r['at_risk_prima_ars']}**.",
    ]
    com = gt["comisiones"]
    lines += [
        "",
        "## Seguimiento de comisiones",
        "",
        f"- Discrepancias (liquidada < esperada): **{len(com['discrepancia_ids'])}** rows, "
        f"total diferencia **ARS {com['total_diferencia_ars']}**.",
        f"- Receivable vencido (período `{com['aged_period']}`, sin liquidar): "
        f"**{len(com['receivable_aged_ids'])}** rows, **ARS {com['receivable_aged_ars']}**.",
    ]
    lc = gt["leads_control"]
    conv = gt["conversion"]
    pipe = gt["pipeline"]
    prof = gt["profitability"]
    ret = gt["retention"]
    lines += [
        "",
        "## Control de leads/cotizaciones",
        "",
        f"- Leads fuera de SLA (sin movimiento): **{lc['sla_breach_count']}**.",
        f"- Cotizaciones emitidas nunca presentadas: **{lc['quotes_no_presentadas_count']}**.",
        "",
        "## Conversión",
        "",
        f"- Leads ganados: **{conv['leads_ganados']}**, perdidos: **{conv['leads_perdidos']}** "
        f"(cerrados: {conv['leads_cerrados']}).",
        f"- Cotizaciones bound (con póliza): **{conv['quotes_bound']}** de "
        f"**{conv['quotes_total_cerradas']}** cerradas.",
        "",
        "## Pipeline",
        "",
        f"- Valor abierto (cotizado/presentado): **ARS {pipe['open_value_ars']}**.",
        "",
        "## Rentabilidad por ramo (controlado)",
        "",
        f"- Ramo `{prof['ramo']}`: prima **ARS {prof['caucion_premium_ars']}**, siniestros "
        f"pagados **ARS {prof['caucion_claims_paid_ars']}**, loss ratio "
        f"**{prof['caucion_loss_ratio']}**.",
        f"- Ramos no rentables (loss ratio > umbral): **{', '.join(prof['unprofitable_ramos'])}**.",
        "",
        "## Retención (comisión en riesgo)",
        "",
        f"- Clientes en riesgo (inactividad + póliza vigente): **{ret['at_risk_count']}**.",
        f"- Comisión en riesgo total: **ARS {ret['comision_en_riesgo_ars']}**.",
        f"- Cliente top en riesgo: `{ret['top_client_id']}`.",
        "",
        "## Clientes inactivos sin póliza vigente",
        "",
        f"- **{gt['inactivos_sin_poliza_count']}** inactive clients with no in-force policy.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
