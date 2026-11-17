"""End-to-end orchestration test with a scripted (fake) LLM - no network.

Drives the real App (plugins, coordinator transfer, sequential pipeline,
parallel dragons, chair/critic loop, HITL confirmation) and asserts the
resulting session state. This guards the wiring, not model quality (that is
covered by `eval/run_eval.py --live`).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

DEAL = "DEAL-2026-003"
DRAGON_TOOLS = {
    "scope_dragon": ("lookup_security_offerings", {"offering_ids": ["OFF-AI-SPR", "OFF-VPCSC"]}),
    "pricing_dragon": ("calculate_engagement_price", {"offering_ids": ["OFF-AI-SPR", "OFF-VPCSC"], "duration_weeks": 10,
                                                       "discount_pct": 5, "proposed_price_usd": 410000}),
    "swimlane_dragon": ("classify_swimlane_ownership", {"offering_ids": ["OFF-AI-SPR", "OFF-VPCSC"], "deal_notes": ""}),
    "delivery_risk_dragon": ("find_available_consultants", {"required_skills": ["ai_security", "vpc_sc"], "region": "EMEA",
                                                            "start_date": "2026-12-01"}),
}
VERDICT = {
    "deal_id": DEAL, "final_decision": "IN", "headline": "All four dragons are in.",
    "dragon_votes": {k: "IN" for k in DRAGON_TOOLS}, "mandatory_conditions": [], "recommended_price_usd": 410000,
    "recommended_staffing": ["C-103"], "swimlane_split": "PSO only", "next_action": "GRANT_TECHNICAL_APPROVAL",
}


def _call(name: str, args: dict) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))]))


def _text(text: str) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


class ScriptedLlm(BaseLlm):
    model: str = "scripted"
    agent_name: str = ""

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        last = llm_request.contents[-1] if llm_request.contents else None
        responded = [p.function_response.name for p in (last.parts if last else []) if p.function_response]
        tools = set(llm_request.tools_dict)
        user_text = " ".join(p.text or "" for p in (last.parts if last else []) if p.text)
        a = self.agent_name
        if a == "deal_dragons_host":
            target = "approval_desk_agent" if "approve" in user_text.lower() else "deal_review_pipeline"
            yield _text("Routing done.") if responded else _call("transfer_to_agent", {"agent_name": target})
        elif a == "deal_intake_agent":
            yield _text("Orbital Grocers, AI-SPR + VPC-SC, $410K.") if responded else _call("fetch_deal_brief", {"deal_id": DEAL})
        elif a in DRAGON_TOOLS:
            tool, args = DRAGON_TOOLS[a]
            if not responded:
                yield _call(tool, args)
            elif responded == [tool]:
                yield _call("record_dragon_verdict", {"dragon": a, "decision": "IN", "confidence": 0.9,
                                                     "rationale": f"{a} checked {tool}; evidence within policy.", "conditions": []})
            else:
                yield _text("I'm in.")
        elif a == "board_chair_agent":
            yield _text(json.dumps(VERDICT))
        elif a == "devils_advocate_agent":
            if not responded:
                yield _call("audit_board_verdict", {})
            elif responded == ["audit_board_verdict"]:
                yield _call("exit_loop", {})
            else:
                yield _text("Verdict is sound.")
        elif a == "approval_desk_agent":
            if not responded and "grant_sow_technical_approval" in tools:
                yield _call("grant_sow_technical_approval", {"deal_id": DEAL, "approved_price_usd": 410000, "conditions": []})
            else:
                yield _text("Approval processed.")
        else:
            yield _text("ok")


def _install_fake(agent) -> None:
    if isinstance(agent, LlmAgent):
        agent.model = ScriptedLlm(agent_name=agent.name)
    for sub in agent.sub_agents or []:
        _install_fake(sub)


def test_full_board_review_and_hitl_pause():
    from deal_dragons.agent import app, build_root_agent

    root = build_root_agent()
    _install_fake(root)
    test_app = app.model_copy(update={"root_agent": root, "events_compaction_config": None, "context_cache_config": None})

    async def run():
        runner = Runner(app=test_app, session_service=InMemorySessionService())
        s = await runner.session_service.create_session(app_name=test_app.name, user_id="u")
        authors = set()
        async for ev in runner.run_async(user_id="u", session_id=s.id, new_message=types.Content(role="user", parts=[types.Part(text=f"Review {DEAL}")])):
            authors.add(ev.author)
        state = (await runner.session_service.get_session(app_name=test_app.name, user_id="u", session_id=s.id)).state
        assert state["deal_brief"]["deal_id"] == DEAL
        assert set(state["dragon_votes"]) == set(DRAGON_TOOLS)
        assert state["board_verdict"]["next_action"] == "GRANT_TECHNICAL_APPROVAL"
        assert state["verdict_audit_issues"] == []
        assert {"scope_dragon", "pricing_dragon", "board_chair_agent", "devils_advocate_agent"} <= authors

        # Second turn: approval must PAUSE for human confirmation, not execute.
        confirmations = []
        async for ev in runner.run_async(user_id="u", session_id=s.id, new_message=types.Content(role="user", parts=[types.Part(text="Please approve it")])):
            confirmations += [c for c in (ev.get_function_calls() or []) if c.name == "adk_request_confirmation"]
        state = (await runner.session_service.get_session(app_name=test_app.name, user_id="u", session_id=s.id)).state
        assert confirmations, "high-stakes tool did not request human confirmation"
        assert f"approval:{DEAL}" not in state, "approval executed without human confirmation"

    asyncio.run(run())
