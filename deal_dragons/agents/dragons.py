"""The four specialist dragons + intake clerk (Gemini Flash, run in parallel)."""

from __future__ import annotations

from google.adk.agents import Agent, ParallelAgent

from deal_dragons import prompts
from deal_dragons.routing import ModelTier, model_for, route_by_deal_complexity
from deal_dragons.tools.deal_tools import (
    calculate_engagement_price,
    check_deal_policy_guardrails,
    classify_swimlane_ownership,
    fetch_deal_brief,
    find_available_consultants,
    list_open_deals,
    lookup_security_offerings,
    record_dragon_verdict,
    register_deal_brief,
)


def build_intake_agent() -> Agent:
    return Agent(
        name="deal_intake_agent",
        description="Fetches or registers the structured deal brief and stores it in session state.",
        model=model_for(ModelTier.FAST),
        instruction=prompts.INTAKE_INSTRUCTION,
        tools=[fetch_deal_brief, register_deal_brief, list_open_deals, lookup_security_offerings],
        output_key="intake_summary",
    )


def _dragon(name: str, description: str, instruction: str, tools: list) -> Agent:
    return Agent(
        name=name,
        description=description,
        model=model_for(ModelTier.FAST),
        instruction=instruction,
        tools=[*tools, record_dragon_verdict],
        output_key=f"{name}_pitch_response",
        before_model_callback=route_by_deal_complexity,  # dynamic Flash -> Pro escalation
    )


def build_dragons_den() -> ParallelAgent:
    """Fan-out: the four dragons grill the deal concurrently (each writes its own state key)."""
    return ParallelAgent(
        name="dragons_den",
        description="Four specialist dragons review scope, pricing, swimlanes and delivery risk in parallel.",
        sub_agents=[
            _dragon("scope_dragon", "Judges scope coherence vs the offering catalog.",
                    prompts.SCOPE_DRAGON_INSTRUCTION, [lookup_security_offerings]),
            _dragon("pricing_dragon", "Judges price, discount, margin and commercial guardrails.",
                    prompts.PRICING_DRAGON_INSTRUCTION, [calculate_engagement_price, check_deal_policy_guardrails]),
            _dragon("swimlane_dragon", "Referees PSO vs Mandiant vs Wiz vs Security FDE ownership.",
                    prompts.SWIMLANE_DRAGON_INSTRUCTION, [classify_swimlane_ownership]),
            _dragon("delivery_risk_dragon", "Judges staffing feasibility and delivery risk.",
                    prompts.DELIVERY_RISK_DRAGON_INSTRUCTION, [lookup_security_offerings, find_available_consultants]),
        ],
    )
