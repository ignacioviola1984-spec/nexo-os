# Nexo canonical data model

> Phase 0 stub — fully specified in Phase 1 alongside the pydantic models and the
> BigQuery DDL. This file is the single source of truth a future engineer reads
> before touching BigQuery.

The schema is the contract: the synthetic data conforms to it exactly, and the
future BigQuery tables match it (same table names, columns, types, grain).

## Tables (domain)
`clientes`, `polizas`, `cuotas`, `comisiones`, `leads`, `cotizaciones`,
`siniestros`, `aseguradoras`, `productores`, `interacciones`.

## Tables (system, written by Nexo)
`acciones` (the HITL inbox), `agent_runs`, `audit_log` (append-only, hash-chained).

Grains, types, PII flags, and the ER overview are filled in Phase 1.
