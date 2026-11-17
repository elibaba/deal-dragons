"""Orchestration tests: multi-agent topology, model routing tiers, app-level configs."""

from google.adk.agents import LlmAgent, LoopAgent, ParallelAgent, SequentialAgent

from deal_dragons.agent import app, root_agent
from deal_dragons.config import settings
from deal_dragons.schemas import BoardVerdict


def _find(agent, name):
    if agent.name == name:
        return agent
    for sub in getattr(agent, "sub_agents", []) or []:
        hit = _find(sub, name)
        if hit:
            return hit
    return None


def test_coordinator_pattern():
    assert isinstance(root_agent, LlmAgent)
    assert {a.name for a in root_agent.sub_agents} == {"deal_review_pipeline", "approval_desk_agent", "deal_historian_agent"}


def test_pipeline_sequential_parallel_loop():
    pipeline = _find(root_agent, "deal_review_pipeline")
    assert isinstance(pipeline, SequentialAgent)
    den = _find(root_agent, "dragons_den")
    assert isinstance(den, ParallelAgent) and len(den.sub_agents) == 4
    loop = _find(root_agent, "verdict_self_eval_loop")
    assert isinstance(loop, LoopAgent) and loop.max_iterations == 3


def test_model_tiers():
    assert _find(root_agent, "board_chair_agent").model.model == settings.pro_model
    for d in ("scope_dragon", "pricing_dragon", "swimlane_dragon", "delivery_risk_dragon", "devils_advocate_agent"):
        assert _find(root_agent, d).model.model == settings.fast_model


def test_chair_output_schema():
    assert _find(root_agent, "board_chair_agent").output_schema is BoardVerdict


def test_app_configuration():
    assert app.name == "deal_dragons"
    assert app.resumability_config.is_resumable
    assert app.events_compaction_config is not None and app.context_cache_config is not None
    names = {p.name for p in app.plugins}
    assert {"deal_guardrails", "intent_outcome_logging"} <= names


def test_constitution_present_everywhere():
    for name in ("deal_dragons_host", "scope_dragon", "board_chair_agent", "approval_desk_agent"):
        assert "Non-negotiable constraints" in _find(root_agent, name).instruction
