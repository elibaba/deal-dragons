"""Self-evaluation helpers for the Devil's Advocate critic loop."""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext
from pydantic import ValidationError

from deal_dragons.schemas import BoardVerdict
from deal_dragons.tools import catalog
from deal_dragons.tools.errors import guided_tool


def audit_board_verdict_rules(verdict: dict[str, Any], recorded_votes: dict[str, Any] | None = None) -> list[str]:
    """Deterministic consistency checks on a Board verdict. Returns a list of issues.

    Args:
        verdict: The Chair's draft BoardVerdict (dict).
        recorded_votes: Votes the dragons actually recorded via `record_dragon_verdict`
            (`{dragon: DragonVerdict dict}`); the Chair must not misreport them.
    """
    issues: list[str] = []
    try:
        v = BoardVerdict.model_validate(verdict)
    except ValidationError as exc:
        return [f"Schema violation: {e['loc']}: {e['msg']}" for e in exc.errors()[:5]]
    pol = catalog.policy()
    reported = v.dragon_votes.model_dump()
    votes = list(v.dragon_votes.model_dump().values())
    if v.next_action == "GRANT_TECHNICAL_APPROVAL" and v.recommended_price_usd < pol["minimum_deal_value_usd"]:
        issues.append("Recommends approval below the $160K minimum deal value.")
    if v.final_decision.value == "IN" and any(d.value == "OUT" for d in votes):
        issues.append("Final decision IN although at least one dragon voted OUT - must be IN_WITH_CONDITIONS or OUT.")
    if v.final_decision.value == "OUT" and v.next_action == "GRANT_TECHNICAL_APPROVAL":
        issues.append("Final decision OUT is inconsistent with next_action GRANT_TECHNICAL_APPROVAL.")
    if v.final_decision.value == "IN_WITH_CONDITIONS" and not v.mandatory_conditions:
        issues.append("IN_WITH_CONDITIONS without mandatory_conditions.")
    for dragon, recorded in (recorded_votes or {}).items():
        actual = recorded.get("decision") if isinstance(recorded, dict) else None
        claimed = reported.get(dragon)
        claimed = getattr(claimed, "value", claimed)
        if actual and claimed != actual:
            issues.append(f"{dragon} actually voted {actual} but the verdict reports {claimed}.")
    return issues


@guided_tool
def audit_board_verdict(tool_context: ToolContext) -> dict[str, Any]:
    """Run deterministic policy & consistency checks on the Chair's draft `board_verdict` in session state.

    Returns:
        dict: `{"status": "success", "passed": bool, "issues": [str]}`. If `passed`
        is true, call `exit_loop`; otherwise write precise feedback for the Chair.
    """
    verdict = tool_context.state.get("board_verdict")
    if not verdict:
        return {"status": "error", "error_code": "NO_DRAFT_VERDICT", "message": "No board_verdict in state yet.",
                "recovery_instructions": "Ask the Chair to produce a verdict first; do not call exit_loop."}
    issues = audit_board_verdict_rules(verdict, tool_context.state.get("dragon_votes"))
    tool_context.state["verdict_audit_issues"] = issues
    return {"status": "success", "passed": not issues, "issues": issues}
