-- Canonical BigQuery DDL for the Nexo data model. GENERATED from nexo_os/data/schema_def.py.
-- Do not edit by hand: edit schema_def.py and re-run scripts/render_ddl.py.
-- Replace the unqualified names with project.dataset-qualified names at deploy time.

-- grain: one row per client
CREATE TABLE IF NOT EXISTS clientes (
  cliente_id STRING NOT NULL,
  tipo STRING NOT NULL,  -- persona_fisica | persona_juridica
  nombre STRING NOT NULL,
  documento STRING NOT NULL,  -- CUIT/DNI
  fecha_nacimiento DATE,
  email STRING,
  telefono STRING,
  localidad STRING NOT NULL,
  provincia STRING NOT NULL,
  segmento STRING NOT NULL,
  fecha_alta DATE NOT NULL,
  productor_id STRING NOT NULL,
  estado STRING NOT NULL  -- activo | inactivo
);

-- grain: one row per policy
CREATE TABLE IF NOT EXISTS polizas (
  poliza_id STRING NOT NULL,
  nro_poliza STRING NOT NULL,
  cliente_id STRING NOT NULL,
  aseguradora_id STRING NOT NULL,
  ramo STRING NOT NULL,  -- auto|hogar|vida|art|caucion|accidentes_personales|comercio|otros
  fecha_inicio_vigencia DATE NOT NULL,
  fecha_fin_vigencia DATE NOT NULL,
  prima_ars NUMERIC NOT NULL,
  suma_asegurada_ars NUMERIC NOT NULL,
  estado STRING NOT NULL,  -- vigente|vencida|anulada|en_gestion|renovada
  forma_pago STRING NOT NULL,
  frecuencia_pago STRING NOT NULL,  -- mensual|trimestral|semestral|anual
  comision_pct NUMERIC NOT NULL,  -- decimal fraction; 0.15 = 15%
  productor_id STRING NOT NULL,
  poliza_origen_id STRING  -- prior-term policy (renewal chain)
);

-- grain: one row per installment of a policy's payment plan
-- note: dias_mora and bucket_mora are DERIVED at read-time relative to the run snapshot date (see core.morosidad); they are NOT stored columns.
CREATE TABLE IF NOT EXISTS cuotas (
  cuota_id STRING NOT NULL,
  poliza_id STRING NOT NULL,
  nro_cuota INT64 NOT NULL,
  fecha_vencimiento DATE NOT NULL,
  monto_ars NUMERIC NOT NULL,
  estado STRING NOT NULL,  -- pendiente|pagada|vencida|parcial
  fecha_pago DATE,
  monto_pagado_ars NUMERIC NOT NULL  -- 0 when unpaid
);

-- grain: one row per commission accrual/settlement event (policy x period)
CREATE TABLE IF NOT EXISTS comisiones (
  comision_id STRING NOT NULL,
  poliza_id STRING NOT NULL,
  aseguradora_id STRING NOT NULL,
  periodo STRING NOT NULL,  -- YYYY-MM
  base_comisionable_ars NUMERIC NOT NULL,
  comision_pct NUMERIC NOT NULL,
  comision_esperada_ars NUMERIC NOT NULL,
  comision_liquidada_ars NUMERIC,
  fecha_liquidacion DATE,
  estado STRING NOT NULL,  -- esperada|liquidada|parcial|con_diferencia
  diferencia_ars NUMERIC NOT NULL  -- esperada - liquidada (settled portion)
);

-- grain: one row per sales opportunity
CREATE TABLE IF NOT EXISTS leads (
  lead_id STRING NOT NULL,
  fecha_ingreso DATE NOT NULL,
  nombre_prospecto STRING NOT NULL,
  contacto STRING NOT NULL,  -- phone/email of prospect
  canal_origen STRING NOT NULL,  -- referido|web|redes|llamado|otro
  ramo STRING NOT NULL,
  productor_id STRING NOT NULL,
  estado STRING NOT NULL,  -- nuevo|contactado|cotizado|presentado|ganado|perdido
  fecha_ultimo_movimiento DATE NOT NULL,
  fecha_cierre DATE,
  motivo_perdida STRING,
  cliente_id STRING  -- set when won
);

-- grain: one row per quote issued for a lead
CREATE TABLE IF NOT EXISTS cotizaciones (
  cotizacion_id STRING NOT NULL,
  lead_id STRING NOT NULL,
  aseguradora_id STRING NOT NULL,
  ramo STRING NOT NULL,
  prima_cotizada_ars NUMERIC NOT NULL,
  fecha_cotizacion DATE NOT NULL,
  estado STRING NOT NULL,  -- emitida|presentada|aceptada|rechazada|vencida
  vigencia_cotizacion DATE,
  poliza_id STRING  -- set when bound -> quote-to-bind
);

-- grain: one row per claim
CREATE TABLE IF NOT EXISTS siniestros (
  siniestro_id STRING NOT NULL,
  poliza_id STRING NOT NULL,
  fecha DATE NOT NULL,
  tipo STRING NOT NULL,
  monto_reclamado_ars NUMERIC NOT NULL,
  monto_pagado_ars NUMERIC,
  estado STRING NOT NULL  -- abierto|en_proceso|pagado|rechazado|cerrado
);

-- grain: reference: one row per insurer
CREATE TABLE IF NOT EXISTS aseguradoras (
  aseguradora_id STRING NOT NULL,
  nombre STRING NOT NULL,
  condiciones_comision_json JSON NOT NULL  -- commission terms by ramo
);

-- grain: reference: one row per broker seat/agent
CREATE TABLE IF NOT EXISTS productores (
  productor_id STRING NOT NULL,
  nombre STRING NOT NULL,
  equipo STRING NOT NULL,
  activo BOOL NOT NULL
);

-- grain: one row per interaction with a client or lead
CREATE TABLE IF NOT EXISTS interacciones (
  interaccion_id STRING NOT NULL,
  entidad_tipo STRING NOT NULL,  -- cliente | lead
  entidad_id STRING NOT NULL,
  fecha DATE NOT NULL,
  tipo STRING NOT NULL,  -- llamado|email|visita|nota
  resumen STRING NOT NULL
);

-- grain: one row per proposed action (the HITL inbox)
CREATE TABLE IF NOT EXISTS acciones (
  accion_id STRING NOT NULL,
  agente STRING NOT NULL,
  tipo_accion STRING NOT NULL,
  entidad_tipo STRING NOT NULL,
  entidad_id STRING NOT NULL,
  prioridad STRING NOT NULL,  -- alta|media|baja
  confianza FLOAT64 NOT NULL,  -- 0..1, deterministic
  monto_en_juego_ars NUMERIC,
  rationale_json JSON NOT NULL,  -- the deterministic numbers behind the action
  mensaje_es STRING NOT NULL,  -- model-drafted Spanish message/recommendation
  estado STRING NOT NULL,  -- propuesta|aprobada|rechazada|editada|vencida
  creada_en TIMESTAMP NOT NULL,
  resuelta_en TIMESTAMP,
  resuelta_por STRING,
  nota_revisor STRING,
  run_id STRING NOT NULL
);

-- grain: one row per orchestrator/agent run
CREATE TABLE IF NOT EXISTS agent_runs (
  run_id STRING NOT NULL,
  iniciado_en TIMESTAMP NOT NULL,
  finalizado_en TIMESTAMP,
  estado STRING NOT NULL,  -- ok|con_warnings|error
  resumen_json JSON NOT NULL,
  data_source STRING NOT NULL,  -- synthetic|bigquery
  data_snapshot_fecha DATE NOT NULL
);

-- grain: one row per event (append-only, hash-chained)
CREATE TABLE IF NOT EXISTS audit_log (
  evento_id STRING NOT NULL,
  ts TIMESTAMP NOT NULL,
  actor STRING NOT NULL,  -- system | user id
  accion STRING NOT NULL,
  entidad_tipo STRING NOT NULL,
  entidad_id STRING,
  detalle_json JSON NOT NULL,  -- identifiers only, never full PII
  prev_hash STRING,
  hash STRING NOT NULL
);
