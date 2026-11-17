"""Tool contract tests: happy paths, explicit schemas and guided error handling."""

from deal_dragons.schemas import GuardrailCheckResult, OfferingLookupResult, PriceQuoteResult, StaffingResult, SwimlaneResult
from deal_dragons.tools import deal_tools as t


def test_fetch_deal_brief_success_writes_state(tool_context):
    res = t.fetch_deal_brief("DEAL-2026-001", tool_context=tool_context)
    assert res["status"] == "success"
    assert tool_context.state["deal_brief"]["customer"] == "Nimbus Telecom"
    assert tool_context.state["user:last_reviewed_deal"] == "DEAL-2026-001"


def test_fetch_deal_brief_bad_format_returns_guided_error(tool_context):
    res = t.fetch_deal_brief("deal one", tool_context=tool_context)
    assert res["status"] == "error"
    assert res["error_code"] == "INVALID_ARGUMENTS"
    assert "call `fetch_deal_brief` again" in res["recovery_instructions"] or "Fix ONLY" in res["recovery_instructions"]


def test_fetch_deal_brief_unknown_id_lists_valid_examples(tool_context):
    res = t.fetch_deal_brief("DEAL-2026-999", tool_context=tool_context)
    assert res["error_code"] == "DEAL_NOT_FOUND"
    assert "DEAL-2026-001" in res["valid_examples"]
    assert "list_open_deals" in res["recovery_instructions"]


def test_lookup_offerings_validates_output_schema():
    res = t.lookup_security_offerings(["OFF-ASTRA", "OFF-NOPE"])
    OfferingLookupResult.model_validate(res)
    assert res["unknown_offering_ids"] == ["OFF-NOPE"]


def test_lookup_offerings_all_unknown_is_guided():
    res = t.lookup_security_offerings(["OFF-NOPE"])
    assert res["error_code"] == "UNKNOWN_OFFERINGS"
    assert "OFF-CSPR" in res["valid_examples"]


def test_price_calculation_math():
    res = t.calculate_engagement_price(["OFF-CSPR"], 6, 10, 150000)
    PriceQuoteResult.model_validate(res)
    assert res["effort_person_days"] == 60.0  # 2 FTE * 6 wks * 5 days
    assert res["discounted_price_usd"] < res["list_price_usd"]


def test_price_rejects_negative_discount():
    res = t.calculate_engagement_price(["OFF-CSPR"], 6, -5, 150000)
    assert res["status"] == "error" and res["error_code"] == "INVALID_ARGUMENTS"


def test_guardrails_min_deal_and_discount():
    res = t.check_deal_policy_guardrails(95000, 20, 40)
    GuardrailCheckResult.model_validate(res)
    rules = {v["rule"]: v["severity"] for v in res["violations"]}
    assert rules == {"MIN_DEAL_VALUE": "BLOCKER", "VP_DISCOUNT_APPROVAL": "WARNING"}
    assert res["passed"] is False


def test_guardrails_absolute_discount_cap():
    res = t.check_deal_policy_guardrails(1_450_000, 35, 30)
    assert any(v["rule"] == "MAX_DISCOUNT" for v in res["violations"])


def test_swimlane_detects_mandiant_and_compliance_promises():
    res = t.classify_swimlane_ownership(["OFF-CSPR", "OFF-PENTEST"], "Customer wants Google to certify ISO 27001 compliance")
    SwimlaneResult.model_validate(res)
    assert any("MANDIANT" in c for c in res["conflicts"])
    assert any("never certifies" in c for c in res["conflicts"])


def test_staffing_excludes_over_utilized():
    res = t.find_available_consultants(["iam", "vpc_sc"], "EMEA", "2026-12-01", 80)
    StaffingResult.model_validate(res)
    assert "C-102" not in {m["consultant_id"] for m in res["matches"]}  # 95% utilized


def test_record_dragon_verdict_requires_conditions(tool_context):
    res = t.record_dragon_verdict("pricing_dragon", "IN_WITH_CONDITIONS", 0.8, "Margin ok but discount needs VP approval.", [], tool_context=tool_context)
    assert res["error_code"] == "MISSING_CONDITIONS"
    ok = t.record_dragon_verdict("pricing_dragon", "IN", 0.8, "Margin 38% and discount 10% within policy.", [], tool_context=tool_context)
    assert ok["status"] == "recorded"
    assert "pricing_dragon" in tool_context.state["dragon_votes"]


def test_technical_approval_blocked_when_board_declined(tool_context):
    tool_context.state["board_verdict"] = {"next_action": "DECLINE"}
    res = t.grant_sow_technical_approval("DEAL-2026-001", 720000, [], tool_context=tool_context)
    assert res["error_code"] == "BOARD_DID_NOT_APPROVE"


def test_soft_booking_unknown_consultant_guided(tool_context):
    res = t.soft_book_consultants("DEAL-2026-001", ["C-999"], "2026-12-01", 4, tool_context=tool_context)
    assert res["error_code"] == "UNKNOWN_CONSULTANTS"


def test_every_tool_has_docstring_with_args():
    tools = [t.fetch_deal_brief, t.list_open_deals, t.register_deal_brief, t.lookup_security_offerings,
             t.calculate_engagement_price, t.check_deal_policy_guardrails, t.classify_swimlane_ownership,
             t.find_available_consultants, t.record_dragon_verdict, t.grant_sow_technical_approval, t.soft_book_consultants]
    for fn in tools:
        doc = fn.__doc__ or ""
        assert len(doc) > 80, fn.__name__
        assert "Returns:" in doc, fn.__name__
        if fn.__code__.co_argcount or fn.__wrapped__.__code__.co_argcount:
            assert "Args:" in doc or fn.__name__ == "list_open_deals", fn.__name__
