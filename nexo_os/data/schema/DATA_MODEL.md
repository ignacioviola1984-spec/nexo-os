# Nexo canonical data model

This file is the single source of truth a future engineer reads before touching
BigQuery. It is kept in sync with code: the tables below are generated from
`nexo_os/data/schema_def.py`, which also renders the canonical DDL (`ddl_bigquery.sql`,
`ddl_sqlite.sql`) and the DuckDB DDL used by the synthetic store, and drives the
PII redaction registry. **Edit `schema_def.py`, then re-run `scripts/render_ddl.py`
and `scripts/render_data_model.py`.**

## Design rules

- **The schema is the contract.** Synthetic data conforms to it exactly; the future
  BigQuery tables match it (same table names, columns, types, grain).
- **Money is exact.** ARS amounts are `NUMERIC` (BigQuery) / `DECIMAL(20,2)`
  (DuckDB), never float. Commission fractions are `NUMERIC` / `DECIMAL(8,6)` and are
  decimal fractions (`0.15` = 15%). On the Turso/libSQL backend, where SQLite has no
  exact NUMERIC, money is stored as `TEXT` (the Decimal's string form) and parsed back
  to Decimal on read — never `REAL` (see `docs/TURSO.md`).
- **Derived fields are not stored.** `cuotas.dias_mora` and `cuotas.bucket_mora`
  (0 / 1-30 / 31-60 / 61-90 / 90+) are computed at read-time relative to the run
  snapshot date (see `core.morosidad`), so aging never disagrees with the snapshot.
- **PII is flagged** (column `PII` below). The redaction helper uses this registry to
  keep full documents/emails/phones/birth dates away from the model and the logs.

## Entity-relationship overview

```
productores 1--* clientes 1--* polizas 1--* cuotas
                                   |  +--* comisiones *--1 aseguradoras
                                   +--* siniestros
leads 1--* cotizaciones *--1 aseguradoras
leads *--1 productores ;  leads 0..1--1 clientes (set when won)
cotizaciones 0..1--1 polizas (set when bound -> quote-to-bind)
polizas 0..1--1 polizas (poliza_origen_id -> renewal chain)
interacciones *-- (cliente | lead)   [polymorphic via entidad_tipo/entidad_id]
```

## Domain tables

### `clientes`

*Grain: one row per client.*

| Column | BQ type | DuckDB type | Null | PII | PK/FK | Notes |
|---|---|---|---|---|---|---|
| `cliente_id` | STRING | VARCHAR |  |  | PK |  |
| `tipo` | STRING | VARCHAR |  |  |  | persona_fisica \| persona_juridica |
| `nombre` | STRING | VARCHAR |  | PII |  |  |
| `documento` | STRING | VARCHAR |  | PII |  | CUIT/DNI |
| `fecha_nacimiento` | DATE | DATE | yes | PII |  |  |
| `email` | STRING | VARCHAR | yes | PII |  |  |
| `telefono` | STRING | VARCHAR | yes | PII |  |  |
| `localidad` | STRING | VARCHAR |  |  |  |  |
| `provincia` | STRING | VARCHAR |  |  |  |  |
| `segmento` | STRING | VARCHAR |  |  |  |  |
| `fecha_alta` | DATE | DATE |  |  |  |  |
| `productor_id` | STRING | VARCHAR |  |  | FK->productores |  |
| `estado` | STRING | VARCHAR |  |  |  | activo \| inactivo |

### `polizas`

*Grain: one row per policy.*

| Column | BQ type | DuckDB type | Null | PII | PK/FK | Notes |
|---|---|---|---|---|---|---|
| `poliza_id` | STRING | VARCHAR |  |  | PK |  |
| `nro_poliza` | STRING | VARCHAR |  |  |  |  |
| `cliente_id` | STRING | VARCHAR |  |  | FK->clientes |  |
| `aseguradora_id` | STRING | VARCHAR |  |  | FK->aseguradoras |  |
| `ramo` | STRING | VARCHAR |  |  |  | auto\|hogar\|vida\|art\|caucion\|accidentes_personales\|comercio\|otros |
| `fecha_inicio_vigencia` | DATE | DATE |  |  |  |  |
| `fecha_fin_vigencia` | DATE | DATE |  |  |  |  |
| `prima_ars` | NUMERIC | DECIMAL(20, 2) |  |  |  |  |
| `suma_asegurada_ars` | NUMERIC | DECIMAL(20, 2) |  |  |  |  |
| `estado` | STRING | VARCHAR |  |  |  | vigente\|vencida\|anulada\|en_gestion\|renovada |
| `forma_pago` | STRING | VARCHAR |  |  |  |  |
| `frecuencia_pago` | STRING | VARCHAR |  |  |  | mensual\|trimestral\|semestral\|anual |
| `comision_pct` | NUMERIC | DECIMAL(8, 6) |  |  |  | decimal fraction; 0.15 = 15% |
| `productor_id` | STRING | VARCHAR |  |  | FK->productores |  |
| `poliza_origen_id` | STRING | VARCHAR | yes |  | FK->polizas | prior-term policy (renewal chain) |

### `cuotas`

*Grain: one row per installment of a policy's payment plan.*

> dias_mora and bucket_mora are DERIVED at read-time relative to the run snapshot date (see core.morosidad); they are NOT stored columns.

| Column | BQ type | DuckDB type | Null | PII | PK/FK | Notes |
|---|---|---|---|---|---|---|
| `cuota_id` | STRING | VARCHAR |  |  | PK |  |
| `poliza_id` | STRING | VARCHAR |  |  | FK->polizas |  |
| `nro_cuota` | INT64 | INTEGER |  |  |  |  |
| `fecha_vencimiento` | DATE | DATE |  |  |  |  |
| `monto_ars` | NUMERIC | DECIMAL(20, 2) |  |  |  |  |
| `estado` | STRING | VARCHAR |  |  |  | pendiente\|pagada\|vencida\|parcial |
| `fecha_pago` | DATE | DATE | yes |  |  |  |
| `monto_pagado_ars` | NUMERIC | DECIMAL(20, 2) |  |  |  | 0 when unpaid |

### `comisiones`

*Grain: one row per commission accrual/settlement event (policy x period).*

| Column | BQ type | DuckDB type | Null | PII | PK/FK | Notes |
|---|---|---|---|---|---|---|
| `comision_id` | STRING | VARCHAR |  |  | PK |  |
| `poliza_id` | STRING | VARCHAR |  |  | FK->polizas |  |
| `aseguradora_id` | STRING | VARCHAR |  |  | FK->aseguradoras |  |
| `periodo` | STRING | VARCHAR |  |  |  | YYYY-MM |
| `base_comisionable_ars` | NUMERIC | DECIMAL(20, 2) |  |  |  |  |
| `comision_pct` | NUMERIC | DECIMAL(8, 6) |  |  |  |  |
| `comision_esperada_ars` | NUMERIC | DECIMAL(20, 2) |  |  |  |  |
| `comision_liquidada_ars` | NUMERIC | DECIMAL(20, 2) | yes |  |  |  |
| `fecha_liquidacion` | DATE | DATE | yes |  |  |  |
| `estado` | STRING | VARCHAR |  |  |  | esperada\|liquidada\|parcial\|con_diferencia |
| `diferencia_ars` | NUMERIC | DECIMAL(20, 2) |  |  |  | esperada - liquidada (settled portion) |

### `leads`

*Grain: one row per sales opportunity.*

| Column | BQ type | DuckDB type | Null | PII | PK/FK | Notes |
|---|---|---|---|---|---|---|
| `lead_id` | STRING | VARCHAR |  |  | PK |  |
| `fecha_ingreso` | DATE | DATE |  |  |  |  |
| `nombre_prospecto` | STRING | VARCHAR |  | PII |  |  |
| `contacto` | STRING | VARCHAR |  | PII |  | phone/email of prospect |
| `canal_origen` | STRING | VARCHAR |  |  |  | referido\|web\|redes\|llamado\|otro |
| `ramo` | STRING | VARCHAR |  |  |  |  |
| `productor_id` | STRING | VARCHAR |  |  | FK->productores |  |
| `estado` | STRING | VARCHAR |  |  |  | nuevo\|contactado\|cotizado\|presentado\|ganado\|perdido |
| `fecha_ultimo_movimiento` | DATE | DATE |  |  |  |  |
| `fecha_cierre` | DATE | DATE | yes |  |  |  |
| `motivo_perdida` | STRING | VARCHAR | yes |  |  |  |
| `cliente_id` | STRING | VARCHAR | yes |  | FK->clientes | set when won |

### `cotizaciones`

*Grain: one row per quote issued for a lead.*

| Column | BQ type | DuckDB type | Null | PII | PK/FK | Notes |
|---|---|---|---|---|---|---|
| `cotizacion_id` | STRING | VARCHAR |  |  | PK |  |
| `lead_id` | STRING | VARCHAR |  |  | FK->leads |  |
| `aseguradora_id` | STRING | VARCHAR |  |  | FK->aseguradoras |  |
| `ramo` | STRING | VARCHAR |  |  |  |  |
| `prima_cotizada_ars` | NUMERIC | DECIMAL(20, 2) |  |  |  |  |
| `fecha_cotizacion` | DATE | DATE |  |  |  |  |
| `estado` | STRING | VARCHAR |  |  |  | emitida\|presentada\|aceptada\|rechazada\|vencida |
| `vigencia_cotizacion` | DATE | DATE | yes |  |  |  |
| `poliza_id` | STRING | VARCHAR | yes |  | FK->polizas | set when bound -> quote-to-bind |

### `siniestros`

*Grain: one row per claim.*

| Column | BQ type | DuckDB type | Null | PII | PK/FK | Notes |
|---|---|---|---|---|---|---|
| `siniestro_id` | STRING | VARCHAR |  |  | PK |  |
| `poliza_id` | STRING | VARCHAR |  |  | FK->polizas |  |
| `fecha` | DATE | DATE |  |  |  |  |
| `tipo` | STRING | VARCHAR |  |  |  |  |
| `monto_reclamado_ars` | NUMERIC | DECIMAL(20, 2) |  |  |  |  |
| `monto_pagado_ars` | NUMERIC | DECIMAL(20, 2) | yes |  |  |  |
| `estado` | STRING | VARCHAR |  |  |  | abierto\|en_proceso\|pagado\|rechazado\|cerrado |

### `aseguradoras`

*Grain: reference: one row per insurer.*

| Column | BQ type | DuckDB type | Null | PII | PK/FK | Notes |
|---|---|---|---|---|---|---|
| `aseguradora_id` | STRING | VARCHAR |  |  | PK |  |
| `nombre` | STRING | VARCHAR |  |  |  |  |
| `condiciones_comision_json` | JSON | VARCHAR |  |  |  | commission terms by ramo |

### `productores`

*Grain: reference: one row per broker seat/agent.*

| Column | BQ type | DuckDB type | Null | PII | PK/FK | Notes |
|---|---|---|---|---|---|---|
| `productor_id` | STRING | VARCHAR |  |  | PK |  |
| `nombre` | STRING | VARCHAR |  |  |  |  |
| `equipo` | STRING | VARCHAR |  |  |  |  |
| `activo` | BOOL | BOOLEAN |  |  |  |  |

### `interacciones`

*Grain: one row per interaction with a client or lead.*

| Column | BQ type | DuckDB type | Null | PII | PK/FK | Notes |
|---|---|---|---|---|---|---|
| `interaccion_id` | STRING | VARCHAR |  |  | PK |  |
| `entidad_tipo` | STRING | VARCHAR |  |  |  | cliente \| lead |
| `entidad_id` | STRING | VARCHAR |  |  |  |  |
| `fecha` | DATE | DATE |  |  |  |  |
| `tipo` | STRING | VARCHAR |  |  |  | llamado\|email\|visita\|nota |
| `resumen` | STRING | VARCHAR |  |  |  |  |

## System tables (written by Nexo itself)

These are produced by the orchestrator and the HITL inbox. `audit_log` is append-only and hash-chained (see SECURITY.md).

### `acciones`

*Grain: one row per proposed action (the HITL inbox).*

| Column | BQ type | DuckDB type | Null | PII | PK/FK | Notes |
|---|---|---|---|---|---|---|
| `accion_id` | STRING | VARCHAR |  |  | PK |  |
| `agente` | STRING | VARCHAR |  |  |  |  |
| `tipo_accion` | STRING | VARCHAR |  |  |  |  |
| `entidad_tipo` | STRING | VARCHAR |  |  |  |  |
| `entidad_id` | STRING | VARCHAR |  |  |  |  |
| `prioridad` | STRING | VARCHAR |  |  |  | alta\|media\|baja |
| `confianza` | FLOAT64 | DOUBLE |  |  |  | 0..1, deterministic |
| `monto_en_juego_ars` | NUMERIC | DECIMAL(20, 2) | yes |  |  |  |
| `rationale_json` | JSON | VARCHAR |  |  |  | the deterministic numbers behind the action |
| `mensaje_es` | STRING | VARCHAR |  |  |  | model-drafted Spanish message/recommendation |
| `estado` | STRING | VARCHAR |  |  |  | propuesta\|aprobada\|rechazada\|editada\|vencida |
| `creada_en` | TIMESTAMP | TIMESTAMP |  |  |  |  |
| `resuelta_en` | TIMESTAMP | TIMESTAMP | yes |  |  |  |
| `resuelta_por` | STRING | VARCHAR | yes |  |  |  |
| `nota_revisor` | STRING | VARCHAR | yes |  |  |  |
| `run_id` | STRING | VARCHAR |  |  | FK->agent_runs |  |

### `agent_runs`

*Grain: one row per orchestrator/agent run.*

| Column | BQ type | DuckDB type | Null | PII | PK/FK | Notes |
|---|---|---|---|---|---|---|
| `run_id` | STRING | VARCHAR |  |  | PK |  |
| `iniciado_en` | TIMESTAMP | TIMESTAMP |  |  |  |  |
| `finalizado_en` | TIMESTAMP | TIMESTAMP | yes |  |  |  |
| `estado` | STRING | VARCHAR |  |  |  | ok\|con_warnings\|error |
| `resumen_json` | JSON | VARCHAR |  |  |  |  |
| `data_source` | STRING | VARCHAR |  |  |  | synthetic\|bigquery |
| `data_snapshot_fecha` | DATE | DATE |  |  |  |  |

### `audit_log`

*Grain: one row per event (append-only, hash-chained).*

| Column | BQ type | DuckDB type | Null | PII | PK/FK | Notes |
|---|---|---|---|---|---|---|
| `evento_id` | STRING | VARCHAR |  |  | PK |  |
| `ts` | TIMESTAMP | TIMESTAMP |  |  |  |  |
| `actor` | STRING | VARCHAR |  |  |  | system \| user id |
| `accion` | STRING | VARCHAR |  |  |  |  |
| `entidad_tipo` | STRING | VARCHAR |  |  |  |  |
| `entidad_id` | STRING | VARCHAR | yes |  |  |  |
| `detalle_json` | JSON | VARCHAR |  |  |  | identifiers only, never full PII |
| `prev_hash` | STRING | VARCHAR | yes |  |  |  |
| `hash` | STRING | VARCHAR |  |  |  |  |
