"""Self-evaluation (Devil's Advocate) deterministic audit tests."""

from deal_dragons.guardrails.self_eval import audit_board_verdict, audit_board_verdict_rules

GOOD = {
    "deal_id": "DEAL-2026-003", "final_decision": "IN", "headline": "We're all in on Orbital Grocers.",
    "dragon_votes": {"scope_dragon": "IN", "pricing_dragon": "IN", "swimlane_dragon": "IN", "delivery_risk_dragon": "IN"},
    "mandatory_conditions": [], "recommended_price_usd": 410000, "recommended_staffing": ["C-103"],
    "swimlane_split": "PSO only", "next_action": "GRANT_TECHNICAL_APPROVAL",
}


def test_good_verdict_passes():
    assert audit_board_verdict_rules(GOOD) == []


def test_inconsistent_verdict_flagged():
    bad = dict(GOOD, dragon_votes=dict(GOOD["dragon_votes"], pricing_dragon="OUT"), recommended_price_usd=90000)
    issues = audit_board_verdict_rules(bad)
    assert any("$160K" in i for i in issues)
    assert any("voted OUT" in i for i in issues)


def test_misreported_vote_flagged():
    recorded = {"pricing_dragon": {"decision": "OUT"}}
    issues = audit_board_verdict_rules(GOOD, recorded)
    assert any("pricing_dragon actually voted OUT" in i for i in issues)


def test_audit_tool_writes_state(tool_context):
    tool_context.state["board_verdict"] = GOOD
    res = audit_board_verdict(tool_context=tool_context)
    assert res["passed"] is True
