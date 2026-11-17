"""Strategic model routing.

Static routing - each agent is pinned to the cheapest model that can do its job:
  * FAST tier (Gemini Flash): intake parsing, the four specialist dragons,
    the Devil's Advocate critic, and memory/history Q&A.
  * PRO tier (Gemini Pro): the Board Chair, which synthesizes conflicting
    votes into a binding verdict.

Dynamic routing - `route_by_deal_complexity` is a `before_model_callback`
that escalates a FAST agent to PRO at request time when the deal is a
"mega-deal" (TCV >= $1M), multi-swimlane, or carries a 25%+ discount, where
shallow reasoning is most expensive.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from deal_dragons.config import settings
from deal_dragons.tools import catalog

logger = logging.getLogger(__name__)

_RETRY = types.HttpRetryOptions(attempts=3, initial_delay=1.0, exp_base=2.0)


class ModelTier(str, Enum):
    FAST = "fast"
    PRO = "pro"


def model_for(tier: ModelTier) -> Gemini:
    """Return a Gemini model (with retry policy) for the requested tier."""
    name = settings.pro_model if tier == ModelTier.PRO else settings.fast_model
    return Gemini(model=name, retry_options=_RETRY)


def deal_complexity_score(deal: dict[str, Any] | None) -> int:
    """Heuristic 0-3 complexity score for a deal brief."""
    if not deal:
        return 0
    pol = catalog.policy()
    cat = catalog.offerings_by_id()
    score = 0
    if float(deal.get("proposed_price_usd", 0)) >= pol["pro_routing_tcv_threshold_usd"]:
        score += 1
    lanes = {cat[o]["owning_swimlane"] for o in deal.get("requested_offerings", []) if o in cat}
    if len(lanes) > 1:
        score += 1
    if float(deal.get("proposed_discount_pct", 0)) >= 25:
        score += 1
    return score


def route_by_deal_complexity(callback_context: CallbackContext, llm_request: LlmRequest) -> LlmResponse | None:
    """before_model_callback: upgrade Flash -> Pro for complex deals (score >= 2)."""
    deal = callback_context.state.get("deal_brief")
    score = deal_complexity_score(deal)
    if score >= 2 and llm_request.model != settings.pro_model:
        logger.info("model_routed", extra={"agent": callback_context.agent_name, "from_model": llm_request.model,
                                           "to_model": settings.pro_model, "complexity_score": score})
        llm_request.model = settings.pro_model
    return None
