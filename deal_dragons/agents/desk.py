"""Approval Desk (HITL-gated actions) and Deal Historian (long-term memory)."""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.tools.load_memory_tool import load_memory_tool
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from deal_dragons import prompts
from deal_dragons.guardrails.hitl import soft_booking_tool, technical_approval_tool
from deal_dragons.routing import ModelTier, model_for
from deal_dragons.tools.deal_tools import find_available_consultants


def build_approval_desk() -> Agent:
    return Agent(
        name="approval_desk_agent",
        description="Executes the Board verdict: grants SOW technical approval / soft-books consultants with human confirmation.",
        model=model_for(ModelTier.FAST),
        instruction=prompts.APPROVAL_DESK_INSTRUCTION,
        tools=[technical_approval_tool, soft_booking_tool, find_available_consultants],
    )


def build_historian() -> Agent:
    return Agent(
        name="deal_historian_agent",
        description="Answers questions about past deal reviews and customer patterns from long-term memory.",
        model=model_for(ModelTier.FAST),
        instruction=prompts.HISTORIAN_INSTRUCTION,
        tools=[PreloadMemoryTool(), load_memory_tool],
    )
