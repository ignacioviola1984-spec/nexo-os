# Production evidence (anonymized)

The live deployment runs privately over the brokerage's real data; that store,
its uploads, users, and audit log are never committed (PII / client
confidentiality). This file is where **anonymized aggregates** from the real
deployment are published — **counts and rates only, never identities** (no names,
documents, emails, phones, policy numbers, or any per-client/per-policy row).

> This is a **template**. Fill the values below from the private deployment; leave
> it as-is until real figures are available. Do not paste anything that could
> identify a client, policy, or person — aggregates only.

## How to produce it (no PII leaves the machine)

These are all roll-ups already computed by the system; export the numbers, not the
rows:

- run one orchestrator cycle on the live backend and read the run summary
  (`python -m nexo_os orchestrate` → `acciones`, `estado`);
- the audit view reports chain integrity and decision counts;
- counts by table/agent are aggregates of the production store.

## Period: `YYYY-MM` (fill in)

| Metric | Value |
|---|---|
| Pólizas bajo gestión (vigentes) | _[fill]_ |
| Prima total en gestión (ARS, redondeada) | _[fill]_ |
| Acciones propuestas (último ciclo) | _[fill]_ |
| Acciones aprobadas / editadas / rechazadas | _[fill]_ |
| % de prosa con grounding verificado | _[fill]_ |
| Cadena de auditoría íntegra (sí/no) | _[fill]_ |
| Reconciliaciones entre agentes en tolerancia (sí/no) | _[fill]_ |

- **No identities**: this table must contain only aggregates. Anything that could
  single out a client/policy/person does **not** belong here.
- The synthetic counterpart (varied datasets, end-to-end) is in
  [`EVIDENCE.md`](EVIDENCE.md) and proves the same pipeline that produces these
  numbers.
