"""The ten specialist agents. Each is a thin Agent: compute() calls its deterministic
core module; propose() (inherited) turns findings into actions with deterministic
confidence/priority; narrate (nexo_os.narrate) writes the Spanish prose."""

from __future__ import annotations

from nexo_os.agents.base import Agent
from nexo_os.core import (
    cartera,
    cobranza,
    comisiones,
    conversion,
    leads_control,
    morosidad,
    pipeline,
    profitability,
    renewals,
    retention,
)
from nexo_os.state import NexoContext


class CarteraAgent(Agent):
    id = "cartera"

    def compute(self, ctx: NexoContext):
        return cartera.compute(ctx.polizas, ctx.thresholds)


class ComisionesAgent(Agent):
    id = "comisiones"

    def compute(self, ctx: NexoContext):
        return comisiones.compute(ctx.comisiones, ctx.snapshot_fecha, ctx.thresholds)


class CobranzaAgent(Agent):
    id = "cobranza"

    def compute(self, ctx: NexoContext):
        return cobranza.compute(ctx.cuotas, ctx.polizas, ctx.snapshot_fecha, ctx.thresholds)


class MorosidadAgent(Agent):
    id = "morosidad"

    def compute(self, ctx: NexoContext):
        return morosidad.compute(ctx.cuotas, ctx.snapshot_fecha, ctx.thresholds)


class RenewalsAgent(Agent):
    id = "renewals"

    def compute(self, ctx: NexoContext):
        return renewals.compute(
            ctx.polizas, ctx.siniestros, ctx.cuotas, ctx.snapshot_fecha, ctx.thresholds
        )


class RetentionAgent(Agent):
    id = "retention"

    def compute(self, ctx: NexoContext):
        return retention.compute(
            ctx.polizas, ctx.cuotas, ctx.interacciones, ctx.snapshot_fecha, ctx.thresholds
        )


class ProfitabilityAgent(Agent):
    id = "profitability"

    def compute(self, ctx: NexoContext):
        return profitability.compute(ctx.polizas, ctx.siniestros, ctx.thresholds)


class ConversionAgent(Agent):
    id = "conversion"

    def compute(self, ctx: NexoContext):
        return conversion.compute(ctx.leads, ctx.cotizaciones, ctx.thresholds)


class PipelineAgent(Agent):
    id = "pipeline"

    def compute(self, ctx: NexoContext):
        return pipeline.compute(ctx.leads, ctx.cotizaciones, ctx.snapshot_fecha, ctx.thresholds)


class LeadsControlAgent(Agent):
    id = "leads_control"

    def compute(self, ctx: NexoContext):
        return leads_control.compute(
            ctx.leads, ctx.cotizaciones, ctx.snapshot_fecha, ctx.thresholds
        )


# Orchestration order: shared figures (cartera/comisiones) first so reconciliations
# downstream have them available.
AGENT_CLASSES: list[type[Agent]] = [
    CarteraAgent,
    ComisionesAgent,
    CobranzaAgent,
    MorosidadAgent,
    RenewalsAgent,
    RetentionAgent,
    ProfitabilityAgent,
    ConversionAgent,
    PipelineAgent,
    LeadsControlAgent,
]


def all_agents() -> list[Agent]:
    return [cls() for cls in AGENT_CLASSES]
