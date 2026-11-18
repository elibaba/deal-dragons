"""Deal Dragons - root agent and ADK App.

Architecture (Coordinator -> Sequential -> Parallel fan-out -> Loop self-eval):

    deal_dragons_host (Coordinator, Flash)
    |-- deal_review_pipeline (SequentialAgent)
    |   |-- deal_intake_agent (Flash)                    -> state.deal_brief
    |   |-- dragons_den (ParallelAgent)                  -> state.dragon_votes
    |   |   |-- scope_dragon | pricing_dragon | swimlane_dragon | delivery_risk_dragon (Flash, dyn. -> Pro)
    |   `-- verdict_self_eval_loop (LoopAgent, max 3)
    |       |-- board_chair_agent (Pro, output_schema=BoardVerdict) -> state.board_verdict
    |       `-- devils_advocate_agent (Flash, audit + exit_loop)
    |-- approval_desk_agent (Flash, HITL-confirmed high-stakes tools)
    `-- deal_historian_agent (Flash, Memory Bank recall)

App-level: guardrail + intent/outcome plugins, token/sliding-window compaction,
context caching, resumability (required for HITL pause/resume).
"""

from __future__ import annotations

import datetime

from google.adk.agents import Agent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.apps.app import ResumabilityConfig
from google.adk.plugins.reflect_retry_tool_plugin import ReflectAndRetryToolPlugin
from google.genai import types

from deal_dragons import prompts
from deal_dragons.agents.board import build_verdict_loop
from deal_dragons.agents.desk import build_approval_desk, build_historian
from deal_dragons.agents.dragons import build_dragons_den, build_intake_agent
from deal_dragons.guardrails.policy_plugin import DealGuardrailPlugin
from deal_dragons.infrastructure.secrets import configure_model_credentials
from deal_dragons.memory.async_memory import schedule_memory_consolidation
from deal_dragons.memory.context_management import build_context_cache_config, build_events_compaction_config
from deal_dragons.observability.intent_outcome import IntentOutcomeLoggingPlugin
from deal_dragons.observability.logging_setup import configure_logging
from deal_dragons.observability.tracing import configure_tracing
from deal_dragons.routing import ModelTier, model_for
from deal_dragons.tools.deal_tools import collect_dragon_votes, list_open_deals

configure_logging()
configure_tracing()
configure_model_credentials()

APP_NAME = "deal_dragons"


async def require_deal_brief(callback_context: CallbackContext) -> types.Content | None:
    """before_agent_callback: skip the expensive dragons if intake produced no valid brief."""
    callback_context.state["current_date"] = datetime.date.today().isoformat()  # grounds date-aware tools
    if not callback_context.state.get("deal_brief"):
        return types.Content(role="model", parts=[types.Part(text=(
            "The dragons are waiting: I need a deal id (DEAL-YYYY-NNN) or the deal details before the review can start."))])
    return None


async def convene_board(callback_context: CallbackContext) -> types.Content | None:
    """before_agent_callback on the verdict loop: require a brief, then aggregate the parallel dragon votes."""
    skip = await require_deal_brief(callback_context)
    if skip:
        return skip
    callback_context.state["dragon_votes"] = collect_dragon_votes(callback_context.state)
    callback_context.state["current_date"] = datetime.date.today().isoformat()
    callback_context.state["verdict_audit_feedback"] = ""
    return None


def build_root_agent() -> Agent:
    dragons_den = build_dragons_den()
    dragons_den.before_agent_callback = require_deal_brief
    verdict_loop = build_verdict_loop()
    verdict_loop.before_agent_callback = convene_board

    pipeline = SequentialAgent(
        name="deal_review_pipeline",
        description="Full Deal Review Board session: intake -> four dragons in parallel -> Chair verdict with self-evaluation.",
        sub_agents=[build_intake_agent(), dragons_den, verdict_loop],
        after_agent_callback=schedule_memory_consolidation,  # async, non-blocking Memory Bank write
    )
    return Agent(
        name="deal_dragons_host",
        description="Coordinator that routes users to the review pipeline, approval desk or historian.",
        model=model_for(ModelTier.FAST),
        instruction=prompts.HOST_INSTRUCTION,
        tools=[list_open_deals],
        sub_agents=[pipeline, build_approval_desk(), build_historian()],
        after_agent_callback=schedule_memory_consolidation,
        generate_content_config=types.GenerateContentConfig(temperature=0.2),
    )


root_agent = build_root_agent()

app = App(
    name=APP_NAME,
    root_agent=root_agent,
    plugins=[
        IntentOutcomeLoggingPlugin(),  # intent vs outcome structured audit trail
        DealGuardrailPlugin(),  # injection screening, PII scrubbing, business policy
        ReflectAndRetryToolPlugin(max_retries=2, throw_exception_if_retry_exceeded=False),
    ],
    events_compaction_config=build_events_compaction_config(),
    context_cache_config=build_context_cache_config(),
    resumability_config=ResumabilityConfig(is_resumable=True),
)
