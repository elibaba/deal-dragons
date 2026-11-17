"""The Board: Chair (Gemini Pro) + Devil's Advocate critic in a self-evaluation LoopAgent."""

from __future__ import annotations

from google.adk.agents import Agent, LoopAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import exit_loop

from deal_dragons import prompts
from deal_dragons.guardrails.self_eval import audit_board_verdict
from deal_dragons.routing import ModelTier, model_for
from deal_dragons.schemas import BoardVerdict


async def _carry_feedback(callback_context: CallbackContext) -> None:
    """after_agent_callback on the critic: hand its feedback to the Chair's next iteration."""
    issues = callback_context.state.get("verdict_audit_issues") or []
    callback_context.state["verdict_audit_feedback"] = "; ".join(issues)
    return None


def build_verdict_loop() -> LoopAgent:
    chair = Agent(
        name="board_chair_agent",
        description="Synthesizes the four dragon votes into a binding, schema-validated BoardVerdict.",
        model=model_for(ModelTier.PRO),  # strategic routing: Pro for synthesis
        instruction=prompts.CHAIR_INSTRUCTION,
        output_schema=BoardVerdict,
        output_key="board_verdict",
        include_contents="none",  # works purely from curated state -> smaller context
    )
    critic = Agent(
        name="devils_advocate_agent",
        description="Self-evaluation critic: audits the Chair's verdict and exits the loop when it is sound.",
        model=model_for(ModelTier.FAST),
        instruction=prompts.DEVILS_ADVOCATE_INSTRUCTION,
        tools=[audit_board_verdict, exit_loop],
        output_key="devils_advocate_notes",
        after_agent_callback=_carry_feedback,
    )
    return LoopAgent(
        name="verdict_self_eval_loop",
        description="Chair drafts a verdict, Devil's Advocate audits it; repeats until it passes (max 3).",
        sub_agents=[chair, critic],
        max_iterations=3,
    )
