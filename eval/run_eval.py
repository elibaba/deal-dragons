"""Automated evaluation harness for Deal Dragons.

Two modes:
  * default (offline, deterministic, runs in every CI build): replays the golden
    dataset through the real tools / policy engine / router and fails on any
    regression (a deal that used to be blocked suddenly passes, a swimlane
    conflict disappears, a mega-deal stops routing to Pro, ...).
  * --live: runs the full multi-agent system end-to-end against Gemini for
    each golden case, captures the tool trajectory + BoardVerdict and scores
    them; additionally runs the ADK `AgentEvaluator` on `deal_dragons.evalset.json`.

Usage:
    python eval/run_eval.py            # offline regression gate
    python eval/run_eval.py --live     # LLM end-to-end eval (needs Vertex AI / API key)
    agents-cli eval deal_dragons --eval-dataset-path eval/deal_dragons.evalset.json --config-path eval/test_config.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deal_dragons.routing import deal_complexity_score  # noqa: E402
from deal_dragons.tools import catalog  # noqa: E402
from deal_dragons.tools import deal_tools as t  # noqa: E402

GOLDEN = json.loads((ROOT / "eval/golden_dataset.json").read_text())["cases"]


class _Ctx:
    def __init__(self) -> None:
        self.state: dict = {}


def evaluate_case_offline(case: dict) -> list[str]:
    """Return a list of regression failures for one golden case (empty = pass)."""
    failures: list[str] = []
    exp = case["expected"]
    ctx = _Ctx()
    brief = t.fetch_deal_brief(case["deal_id"], tool_context=ctx)["deal"]
    quote = t.calculate_engagement_price(brief["requested_offerings"], brief["duration_weeks"],
                                         brief["proposed_discount_pct"], brief["proposed_price_usd"])
    guard = t.check_deal_policy_guardrails(brief["proposed_price_usd"], brief["proposed_discount_pct"], quote["gross_margin_pct"])
    blockers = sorted(v["rule"] for v in guard["violations"] if v["severity"] == "BLOCKER")
    if guard["passed"] != exp["guardrails_passed"]:
        failures.append(f"guardrails_passed={guard['passed']} expected {exp['guardrails_passed']}")
    for rule in exp["blocker_rules"]:
        if rule not in blockers:
            failures.append(f"missing BLOCKER {rule} (got {blockers})")
    lanes = t.classify_swimlane_ownership(brief["requested_offerings"], brief["notes"])
    conflicts = " ".join(lanes["conflicts"])
    for kw in exp["swimlane_conflict_keywords"]:
        if kw not in conflicts:
            failures.append(f"swimlane conflict '{kw}' not detected")
    if not exp["swimlane_conflict_keywords"] and lanes["conflicts"]:
        failures.append(f"unexpected swimlane conflicts {lanes['conflicts']}")
    if exp.get("routes_to_pro") and deal_complexity_score(brief) < 2:
        failures.append("complex deal no longer routes to Pro")
    return failures


def run_offline() -> int:
    total, failed = 0, 0
    for case in GOLDEN:
        total += 1
        fails = evaluate_case_offline(case)
        status = "PASS" if not fails else "FAIL"
        print(json.dumps({"case": case["case_id"], "status": status, "failures": fails}))
        failed += bool(fails)
    print(json.dumps({"summary": {"total": total, "failed": failed, "pass_rate": (total - failed) / total}}))
    return 1 if failed else 0


async def _run_live_case(case: dict) -> dict:  # pragma: no cover - needs Gemini
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from deal_dragons.agent import app

    runner = Runner(app=app, session_service=InMemorySessionService())
    session = await runner.session_service.create_session(app_name=app.name, user_id="eval")
    tools_called: list[str] = []
    msg = types.Content(role="user", parts=[types.Part(text=f"Run a full board review of {case['deal_id']}.")])
    async for event in runner.run_async(user_id="eval", session_id=session.id, new_message=msg):
        for call in event.get_function_calls() or []:
            tools_called.append(call.name)
    final = await runner.session_service.get_session(app_name=app.name, user_id="eval", session_id=session.id)
    verdict = final.state.get("board_verdict") or {}
    exp = case["expected"]
    missing = [tname for tname in exp["required_tools"] if tname not in tools_called]
    decision_ok = verdict.get("final_decision") in exp["final_decision_in"]
    return {"case": case["case_id"], "decision": verdict.get("final_decision"), "decision_ok": decision_ok,
            "missing_tools": missing, "passed": decision_ok and not missing, "run_id": uuid.uuid4().hex[:8]}


async def run_live() -> int:  # pragma: no cover - needs Gemini
    results = [await _run_live_case(c) for c in GOLDEN]
    for r in results:
        print(json.dumps(r))
    from google.adk.evaluation.agent_evaluator import AgentEvaluator

    await AgentEvaluator.evaluate("deal_dragons", str(ROOT / "eval/deal_dragons.evalset.json"), num_runs=1)
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="run end-to-end LLM evaluation")
    args = parser.parse_args()
    catalog._load.cache_clear()
    sys.exit(asyncio.run(run_live()) if args.live else run_offline())
