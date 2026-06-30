-- Canonical SQLite/libSQL DDL for the Nexo Turso backend. GENERATED from nexo_os/data/schema_def.py.
-- Do not edit by hand: edit schema_def.py and re-run scripts/render_ddl.py.
-- Money (MONEY/PCT) is TEXT (Decimal as string); dates/timestamps are ISO TEXT;
-- booleans are INTEGER 0/1. The Turso backend creates tables from this contract.

-- grain: one row per client
CREATE TABLE IF NOT EXISTS clientes (
  cliente_id TEXT NOT NULL,
  tipo TEXT NOT NULL,  -- persona_fisica | persona_juridica
  nombre TEXT NOT NULL,
  documento TEXT NOT NULL,  -- CUIT/DNI
  fecha_nacimiento TEXT,
  email TEXT,
  telefono TEXT,
  localidad TEXT NOT NULL,
  provincia TEXT NOT NULL,
  segmento TEXT NOT NULL,
  fecha_alta TEXT NOT NULL,
  productor_id TEXT NOT NULL,
  estado TEXT NOT NULL,  -- activo | inactivo
  PRIMARY KEY (cliente_id)
);

-- grain: one row per policy
CREATE TABLE IF NOT EXISTS polizas (
  poliza_id TEXT NOT NULL,
  nro_poliza TEXT NOT NULL,
  cliente_id TEXT NOT NULL,
  aseguradora_id TEXT NOT NULL,
  ramo TEXT NOT NULL,  -- auto|hogar|vida|art|caucion|accidentes_personales|comercio|otros
  fecha_inicio_vigencia TEXT NOT NULL,
  fecha_fin_vigencia TEXT NOT NULL,
  prima_ars TEXT NOT NULL,
  suma_asegurada_ars TEXT NOT NULL,
  estado TEXT NOT NULL,  -- vigente|vencida|anulada|en_gestion|renovada
  forma_pago TEXT NOT NULL,
  frecuencia_pago TEXT NOT NULL,  -- mensual|trimestral|semestral|anual
  comision_pct TEXT NOT NULL,  -- decimal fraction; 0.15 = 15%
  productor_id TEXT NOT NULL,
  poliza_origen_id TEXT,  -- prior-term policy (renewal chain)
  PRIMARY KEY (poliza_id)
);

-- grain: one row per installment of a policy's payment plan
-- note: dias_mora and bucket_mora are DERIVED at read-time relative to the run snapshot date (see core.morosidad); they are NOT stored columns.
CREATE TABLE IF NOT EXISTS cuotas (
  cuota_id TEXT NOT NULL,
  poliza_id TEXT NOT NULL,
  nro_cuota INTEGER NOT NULL,
  fecha_vencimiento TEXT NOT NULL,
  monto_ars TEXT NOT NULL,
  estado TEXT NOT NULL,  -- pendiente|pagada|vencida|parcial
  fecha_pago TEXT,
  monto_pagado_ars TEXT NOT NULL,  -- 0 when unpaid
  PRIMARY KEY (cuota_id)
);

-- grain: one row per commission accrual/settlement event (policy x period)
CREATE TABLE IF NOT EXISTS comisiones (
  comision_id TEXT NOT NULL,
  poliza_id TEXT NOT NULL,
  aseguradora_id TEXT NOT NULL,
  periodo TEXT NOT NULL,  -- YYYY-MM
  base_comisionable_ars TEXT NOT NULL,
  comision_pct TEXT NOT NULL,
  comision_esperada_ars TEXT NOT NULL,
  comision_liquidada_ars TEXT,
  fecha_liquidacion TEXT,
  estado TEXT NOT NULL,  -- esperada|liquidada|parcial|con_diferencia
  diferencia_ars TEXT NOT NULL,  -- esperada - liquidada (settled portion)
  PRIMARY KEY (comision_id)
);

-- grain: one row per sales opportunity
CREATE TABLE IF NOT EXISTS leads (
  lead_id TEXT NOT NULL,
  fecha_ingreso TEXT NOT NULL,
  nombre_prospecto TEXT NOT NULL,
  contacto TEXT NOT NULL,  -- phone/email of prospect
  canal_origen TEXT NOT NULL,  -- referido|web|redes|llamado|otro
  ramo TEXT NOT NULL,
  productor_id TEXT NOT NULL,
  estado TEXT NOT NULL,  -- nuevo|contactado|cotizado|presentado|ganado|perdido
  fecha_ultimo_movimiento TEXT NOT NULL,
  fecha_cierre TEXT,
  motivo_perdida TEXT,
  cliente_id TEXT,  -- set when won
  PRIMARY KEY (lead_id)
);

-- grain: one row per quote issued for a lead
CREATE TABLE IF NOT EXISTS cotizaciones (
  cotizacion_id TEXT NOT NULL,
  lead_id TEXT NOT NULL,
  aseguradora_id TEXT NOT NULL,
  ramo TEXT NOT NULL,
  prima_cotizada_ars TEXT NOT NULL,
  fecha_cotizacion TEXT NOT NULL,
  estado TEXT NOT NULL,  -- emitida|presentada|aceptada|rechazada|vencida
  vigencia_cotizacion TEXT,
  poliza_id TEXT,  -- set when bound -> quote-to-bind
  PRIMARY KEY (cotizacion_id)
);

-- grain: one row per claim
CREATE TABLE IF NOT EXISTS siniestros (
  siniestro_id TEXT NOT NULL,
  poliza_id TEXT NOT NULL,
  fecha TEXT NOT NULL,
  tipo TEXT NOT NULL,
  monto_reclamado_ars TEXT NOT NULL,
  monto_pagado_ars TEXT,
  estado TEXT NOT NULL,  -- abierto|en_proceso|pagado|rechazado|cerrado
  PRIMARY KEY (siniestro_id)
);

-- grain: reference: one row per insurer
CREATE TABLE IF NOT EXISTS aseguradoras (
  aseguradora_id TEXT NOT NULL,
  nombre TEXT NOT NULL,
  condiciones_comision_json TEXT NOT NULL,  -- commission terms by ramo
  PRIMARY KEY (aseguradora_id)
);

-- grain: reference: one row per broker seat/agent
CREATE TABLE IF NOT EXISTS productores (
  productor_id TEXT NOT NULL,
  nombre TEXT NOT NULL,
  equipo TEXT NOT NULL,
  activo INTEGER NOT NULL,
  PRIMARY KEY (productor_id)
);

-- grain: one row per interaction with a client or lead
CREATE TABLE IF NOT EXISTS interacciones (
  interaccion_id TEXT NOT NULL,
  entidad_tipo TEXT NOT NULL,  -- cliente | lead
  entidad_id TEXT NOT NULL,
  fecha TEXT NOT NULL,
  tipo TEXT NOT NULL,  -- llamado|email|visita|nota
  resumen TEXT NOT NULL,
  PRIMARY KEY (interaccion_id)
);

-- grain: one row per proposed action (the HITL inbox)
CREATE TABLE IF NOT EXISTS acciones (
  accion_id TEXT NOT NULL,
  agente TEXT NOT NULL,
  tipo_accion TEXT NOT NULL,
  entidad_tipo TEXT NOT NULL,
  entidad_id TEXT NOT NULL,
  prioridad TEXT NOT NULL,  -- alta|media|baja
  confianza REAL NOT NULL,  -- 0..1, deterministic
  monto_en_juego_ars TEXT,
  rationale_json TEXT NOT NULL,  -- the deterministic numbers behind the action
  mensaje_es TEXT NOT NULL,  -- model-drafted Spanish message/recommendation
  estado TEXT NOT NULL,  -- propuesta|aprobada|rechazada|editada|vencida
  creada_en TEXT NOT NULL,
  resuelta_en TEXT,
  resuelta_por TEXT,
  nota_revisor TEXT,
  run_id TEXT NOT NULL,
  PRIMARY KEY (accion_id)
);

-- grain: one row per orchestrator/agent run
CREATE TABLE IF NOT EXISTS agent_runs (
  run_id TEXT NOT NULL,
  iniciado_en TEXT NOT NULL,
  finalizado_en TEXT,
  estado TEXT NOT NULL,  -- ok|con_warnings|error
  resumen_json TEXT NOT NULL,
  data_source TEXT NOT NULL,  -- synthetic|bigquery
  data_snapshot_fecha TEXT NOT NULL,
  PRIMARY KEY (run_id)
);

-- grain: one row per event (append-only, hash-chained)
CREATE TABLE IF NOT EXISTS audit_log (
  evento_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,  -- system | user id
  accion TEXT NOT NULL,
  entidad_tipo TEXT NOT NULL,
  entidad_id TEXT,
  detalle_json TEXT NOT NULL,  -- identifiers only, never full PII
  prev_hash TEXT,
  hash TEXT NOT NULL,
  PRIMARY KEY (evento_id)
);
