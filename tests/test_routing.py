"""Strategic model routing tests."""

from types import SimpleNamespace

from google.adk.models.llm_request import LlmRequest

from deal_dragons.config import settings
from deal_dragons.routing import deal_complexity_score, route_by_deal_complexity


def test_complexity_score():
    assert deal_complexity_score(None) == 0
    mega = {"proposed_price_usd": 1_450_000, "requested_offerings": ["OFF-SCC-WIZ", "OFF-CSPR"], "proposed_discount_pct": 35}
    assert deal_complexity_score(mega) == 3


def test_complex_deal_routes_to_pro():
    ctx = SimpleNamespace(agent_name="pricing_dragon", state={"deal_brief": {
        "proposed_price_usd": 1_450_000, "requested_offerings": ["OFF-SCC-WIZ", "OFF-CSPR"], "proposed_discount_pct": 5}})
    req = LlmRequest(model=settings.fast_model)
    route_by_deal_complexity(ctx, req)
    assert req.model == settings.pro_model


def test_simple_deal_stays_on_flash():
    ctx = SimpleNamespace(agent_name="scope_dragon", state={"deal_brief": {
        "proposed_price_usd": 300_000, "requested_offerings": ["OFF-CSPR"], "proposed_discount_pct": 5}})
    req = LlmRequest(model=settings.fast_model)
    route_by_deal_complexity(ctx, req)
    assert req.model == settings.fast_model
