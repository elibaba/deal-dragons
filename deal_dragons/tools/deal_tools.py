"""Domain tools used by the Deal Dragons agents.

Every tool:
  * has a specific, action-oriented name (`calculate_engagement_price`, not `pricing`);
  * documents its purpose, every argument and its return shape (ADK turns the
    docstring + type hints into the function declaration the LLM sees);
  * validates inputs against an explicit Pydantic schema (`deal_dragons.schemas`);
  * returns a validated output schema, or a guided `ToolError` with recovery
    instructions instead of raising;
  * emits an OpenTelemetry span so it shows up in the distributed trace.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from typing import Any

from google.adk.tools import ToolContext
from opentelemetry import trace

from deal_dragons.schemas import (
    ConsultantMatch,
    DealBrief,
    DragonVerdict,
    FetchDealBriefRequest,
    GuardrailCheckRequest,
    GuardrailCheckResult,
    Offering,
    OfferingLookupRequest,
    OfferingLookupResult,
    PolicyViolation,
    PriceQuoteRequest,
    PriceQuoteResult,
    SoftBookingRequest,
    SoftBookingResult,
    StaffingRequest,
    StaffingResult,
    Swimlane,
    SwimlaneAssignment,
    SwimlaneRequest,
    SwimlaneResult,
    TechnicalApprovalRequest,
    TechnicalApprovalResult,
)
from deal_dragons.tools import catalog
from deal_dragons.tools.errors import DealDragonsToolError, guided_tool

tracer = trace.get_tracer("deal_dragons.tools")

# Keywords that indicate work outside the PSO swimlane.
_MANDIANT_SIGNALS = re.compile(r"\b(forensic|breach investigation|pen(etration)?[ -]?test|red team|incident response retainer)\b", re.I)
_COMPLIANCE_PROMISE = re.compile(r"\b(certify|certification|guarantee)\b.*\b(iso ?27001|soc ?2|pci|hipaa|compliance)\b", re.I)


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------
@guided_tool
def fetch_deal_brief(deal_id: str, tool_context: ToolContext) -> dict[str, Any]:
    """Fetch the structured deal brief for a PSO Security opportunity from the CRM.

    Use this FIRST whenever the user mentions a deal id. The brief is also saved
    to session state under `deal_brief` so every dragon reviews the same facts.

    Args:
        deal_id: CRM opportunity id in the format `DEAL-YYYY-NNN`, e.g. `DEAL-2026-001`.

    Returns:
        dict: `{"status": "success", "deal": DealBrief}` on success, or a
        `ToolError` dict (`status="error"`) with `recovery_instructions`.
    """
    with tracer.start_as_current_span("tool.fetch_deal_brief") as span:
        req = FetchDealBriefRequest.model_validate({"deal_id": deal_id})
        span.set_attribute("deal.id", req.deal_id)
        deals = catalog.deals_by_id()
        if req.deal_id not in deals:
            raise DealDragonsToolError(
                "DEAL_NOT_FOUND",
                f"No deal with id {req.deal_id} exists in the pipeline.",
                "Ask the user to confirm the deal id, or call `list_open_deals` to show valid ids. "
                "If the user pasted deal details instead, call `register_deal_brief` with them.",
                valid_examples=sorted(deals)[:4],
            )
        brief = DealBrief.model_validate(deals[req.deal_id])
        tool_context.state["deal_brief"] = brief.model_dump(mode="json")
        tool_context.state["user:last_reviewed_deal"] = brief.deal_id
        return {"status": "success", "deal": brief.model_dump(mode="json")}


@guided_tool
def list_open_deals() -> dict[str, Any]:
    """List the open PSO Security deals awaiting a Deal Review Board session.

    Returns:
        dict: `{"status": "success", "deals": [{"deal_id", "customer", "proposed_price_usd"}]}`.
    """
    deals = [
        {"deal_id": d["deal_id"], "customer": d["customer"], "proposed_price_usd": d["proposed_price_usd"]}
        for d in catalog.deals_by_id().values()
    ]
    return {"status": "success", "deals": deals}


@guided_tool
def register_deal_brief(
    deal_id: str,
    customer: str,
    industry: str,
    region: str,
    requested_offerings: list[str],
    proposed_price_usd: float,
    proposed_discount_pct: float,
    duration_weeks: int,
    notes: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Register a NEW deal brief pasted by the user (not yet in the CRM) for review.

    Args:
        deal_id: New id in the format `DEAL-YYYY-NNN`.
        customer: Customer legal name.
        industry: Industry vertical, e.g. `financial_services`.
        region: One of `EMEA`, `MENAT`, `NA`, `JAPAC`, `LATAM`.
        requested_offerings: Offering ids such as `OFF-CSPR`, `OFF-ASTRA` (call
            `lookup_security_offerings` if unsure).
        proposed_price_usd: Total contract value proposed to the customer, in USD.
        proposed_discount_pct: Discount off list price, 0-100.
        duration_weeks: Engagement length in weeks.
        notes: Free-text scoping notes from the account team.

    Returns:
        dict: `{"status": "success", "deal": DealBrief}` or a guided `ToolError`.
    """
    brief = DealBrief.model_validate(
        {
            "deal_id": deal_id,
            "customer": customer,
            "industry": industry,
            "region": region,
            "requested_offerings": requested_offerings,
            "proposed_price_usd": proposed_price_usd,
            "proposed_discount_pct": proposed_discount_pct,
            "duration_weeks": duration_weeks,
            "notes": notes,
        }
    )
    tool_context.state["deal_brief"] = brief.model_dump(mode="json")
    return {"status": "success", "deal": brief.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Scope dragon
# ---------------------------------------------------------------------------
@guided_tool
def lookup_security_offerings(offering_ids: list[str]) -> dict[str, Any]:
    """Look up PSO Security catalog offerings (scope, typical weeks/FTE, skills, owning swimlane).

    Args:
        offering_ids: One or more offering ids, e.g. `["OFF-ASTRA", "OFF-CSPR"]`.

    Returns:
        dict: `OfferingLookupResult` with `offerings` and any `unknown_offering_ids`.
    """
    with tracer.start_as_current_span("tool.lookup_security_offerings"):
        req = OfferingLookupRequest.model_validate({"offering_ids": offering_ids})
        cat = catalog.offerings_by_id()
        found = [Offering.model_validate(cat[o]) for o in req.offering_ids if o in cat]
        unknown = [o for o in req.offering_ids if o not in cat]
        if not found:
            raise DealDragonsToolError(
                "UNKNOWN_OFFERINGS",
                f"None of {unknown} are in the PSO Security catalog.",
                "Use catalog ids exactly as listed in `valid_examples`; map free-text requests "
                "(e.g. 'SIEM migration') to the closest id before retrying.",
                valid_examples=sorted(cat),
            )
        return OfferingLookupResult(offerings=found, unknown_offering_ids=unknown).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Pricing dragon
# ---------------------------------------------------------------------------
def _blended_daily_rate() -> float:
    card = catalog.rate_card()
    return sum(card["daily_rates"][lvl] * share for lvl, share in card["default_level_mix"].items())


@guided_tool
def calculate_engagement_price(
    offering_ids: list[str], duration_weeks: int, discount_pct: float, proposed_price_usd: float
) -> dict[str, Any]:
    """Calculate list price, discounted price, cost and gross margin for a proposed engagement.

    Effort = sum(typical_fte of each offering) x duration_weeks x 5 days, priced at
    the blended daily rate of the rate card.

    Args:
        offering_ids: Catalog offering ids in scope, e.g. `["OFF-AI-SPR", "OFF-VPCSC"]`.
        duration_weeks: Engagement length in weeks (1-104).
        discount_pct: Discount off list price the account team proposes (0-100).
        proposed_price_usd: Price the account team intends to put in the SOW (USD).

    Returns:
        dict: `PriceQuoteResult` (list/discounted/proposed price, cost, gross_margin_pct,
        effort_person_days, price_gap_pct) or a guided `ToolError`.
    """
    with tracer.start_as_current_span("tool.calculate_engagement_price") as span:
        req = PriceQuoteRequest.model_validate(
            {
                "offering_ids": offering_ids,
                "duration_weeks": duration_weeks,
                "discount_pct": discount_pct,
                "proposed_price_usd": proposed_price_usd,
            }
        )
        cat = catalog.offerings_by_id()
        unknown = [o for o in req.offering_ids if o not in cat]
        if unknown:
            raise DealDragonsToolError(
                "UNKNOWN_OFFERINGS",
                f"Cannot price unknown offerings {unknown}.",
                "Remove or correct the unknown ids (see `valid_examples`) and call "
                "`calculate_engagement_price` again.",
                valid_examples=sorted(cat),
            )
        card = catalog.rate_card()
        fte = sum(cat[o]["typical_fte"] for o in req.offering_ids)
        person_days = fte * req.duration_weeks * card["working_days_per_week"]
        list_price = person_days * _blended_daily_rate()
        discounted = list_price * (1 - req.discount_pct / 100)
        cost = list_price * card["policy"]["fully_loaded_cost_ratio"]
        margin = (req.proposed_price_usd - cost) / req.proposed_price_usd * 100
        gap = (req.proposed_price_usd - discounted) / discounted * 100
        span.set_attribute("deal.gross_margin_pct", round(margin, 2))
        return PriceQuoteResult(
            list_price_usd=round(list_price, 2),
            discounted_price_usd=round(discounted, 2),
            proposed_price_usd=req.proposed_price_usd,
            estimated_cost_usd=round(cost, 2),
            gross_margin_pct=round(margin, 2),
            effort_person_days=round(person_days, 1),
            price_gap_pct=round(gap, 2),
        ).model_dump(mode="json")


@guided_tool
def check_deal_policy_guardrails(deal_value_usd: float, discount_pct: float, gross_margin_pct: float) -> dict[str, Any]:
    """Check a deal against PSO Security commercial guardrails.

    Rules: minimum deal value ($160K), discount above 15% needs VP sign-off,
    discount above 30% is never allowed, gross margin must be >= 25%.

    Args:
        deal_value_usd: Total contract value in USD.
        discount_pct: Discount off list price (0-100).
        gross_margin_pct: Gross margin from `calculate_engagement_price`.

    Returns:
        dict: `GuardrailCheckResult` with `passed` and a list of `violations`
        (each with severity BLOCKER/WARNING and a `remediation`).
    """
    req = GuardrailCheckRequest.model_validate(
        {"deal_value_usd": deal_value_usd, "discount_pct": discount_pct, "gross_margin_pct": gross_margin_pct}
    )
    pol = catalog.policy()
    v: list[PolicyViolation] = []
    if req.deal_value_usd < pol["minimum_deal_value_usd"]:
        v.append(PolicyViolation(
            rule="MIN_DEAL_VALUE", severity="BLOCKER",
            message=f"${req.deal_value_usd:,.0f} is below the ${pol['minimum_deal_value_usd']:,.0f} practice minimum.",
            remediation="Bundle with adjacent scope (e.g. VPC-SC rollout) or route to a partner / Delivery Navigator self-serve.",
        ))
    if req.discount_pct > pol["absolute_max_discount_pct"]:
        v.append(PolicyViolation(
            rule="MAX_DISCOUNT", severity="BLOCKER",
            message=f"{req.discount_pct}% exceeds the absolute {pol['absolute_max_discount_pct']}% discount cap.",
            remediation="Reduce scope instead of price, or fund via an approved investment program.",
        ))
    elif req.discount_pct > pol["max_discount_pct_without_vp"]:
        v.append(PolicyViolation(
            rule="VP_DISCOUNT_APPROVAL", severity="WARNING",
            message=f"{req.discount_pct}% discount requires VP approval (> {pol['max_discount_pct_without_vp']}%).",
            remediation="Attach VP approval to the deal before technical approval.",
        ))
    if req.gross_margin_pct < pol["min_gross_margin_pct"]:
        v.append(PolicyViolation(
            rule="MIN_MARGIN", severity="BLOCKER",
            message=f"Gross margin {req.gross_margin_pct:.1f}% is below the {pol['min_gross_margin_pct']}% floor.",
            remediation="Increase price, shift level mix to L4/L5, or shorten duration.",
        ))
    passed = not any(x.severity == "BLOCKER" for x in v)
    return GuardrailCheckResult(passed=passed, violations=v).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Swimlane dragon
# ---------------------------------------------------------------------------
@guided_tool
def classify_swimlane_ownership(offering_ids: list[str], deal_notes: str = "") -> dict[str, Any]:
    """Decide which Google security team owns each requested item: PSO, Mandiant, Wiz or Security FDE.

    Also scans the deal notes for out-of-swimlane asks (forensics, pen-testing)
    and for compliance-certification promises PSO must never make.

    Args:
        offering_ids: Catalog offering ids in scope.
        deal_notes: Free-text notes from the deal brief.

    Returns:
        dict: `SwimlaneResult` with per-offering `assignments`, `conflicts`, and a
        `recommended_split` sentence.
    """
    req = SwimlaneRequest.model_validate({"offering_ids": offering_ids, "deal_notes": deal_notes})
    cat = catalog.offerings_by_id()
    assignments: list[SwimlaneAssignment] = []
    conflicts: list[str] = []
    for oid in req.offering_ids:
        if oid not in cat:
            conflicts.append(f"{oid}: unknown offering - cannot assign a swimlane.")
            continue
        owner = Swimlane(cat[oid]["owning_swimlane"])
        assignments.append(SwimlaneAssignment(offering_id=oid, owner=owner, pso_can_sell=owner == Swimlane.PSO))
        if owner != Swimlane.PSO:
            conflicts.append(f"{oid} is owned by {owner.value}; it must be contracted separately or co-sold.")
    if _MANDIANT_SIGNALS.search(req.deal_notes):
        conflicts.append("Notes request forensic/offensive work: route to MANDIANT, PSO must not deliver it.")
    if _COMPLIANCE_PROMISE.search(req.deal_notes):
        conflicts.append("Notes ask Google to certify/guarantee compliance: PSO advises on controls, it never certifies.")
    others = sorted({a.owner.value for a in assignments if a.owner != Swimlane.PSO})
    split = "PSO only" if not others and not conflicts else f"PSO + {', '.join(others) or 'MANDIANT'} (separate contracts)"
    return SwimlaneResult(assignments=assignments, conflicts=conflicts, recommended_split=split).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Delivery-risk dragon
# ---------------------------------------------------------------------------
@guided_tool
def find_available_consultants(
    required_skills: list[str], region: str, start_date: str, max_utilization_pct: int = 80
) -> dict[str, Any]:
    """Find bench consultants who match the required skills and have capacity.

    Args:
        required_skills: Skill tags from the offering catalog, e.g. `["secops", "soar"]`.
        region: Delivery region: `EMEA`, `MENAT`, `NA`, `JAPAC` or `LATAM`.
        start_date: Planned start date `YYYY-MM-DD`.
        max_utilization_pct: Exclude consultants already above this utilization (default 80).

    Returns:
        dict: `StaffingResult` with ranked `matches` and `uncovered_skills`.
    """
    req = StaffingRequest.model_validate(
        {"required_skills": required_skills, "region": region, "start_date": start_date,
         "max_utilization_pct": max_utilization_pct}
    )
    start = dt.date.fromisoformat(req.start_date)
    pool = [c for c in catalog.consultants() if c["region"] in {req.region, "EMEA" if req.region == "MENAT" else req.region}]
    matches: list[ConsultantMatch] = []
    for c in pool:
        skills = sorted(set(c["skills"]) & set(req.required_skills))
        if not skills or c["utilization_pct"] > req.max_utilization_pct:
            continue
        if dt.date.fromisoformat(c["available_from"]) > start + dt.timedelta(days=21):
            continue
        matches.append(ConsultantMatch(
            consultant_id=c["consultant_id"], alias=c["alias"], level=c["level"], matched_skills=skills,
            utilization_pct=c["utilization_pct"], available_from=c["available_from"],
        ))
    matches.sort(key=lambda m: (-len(m.matched_skills), m.utilization_pct))
    covered = {s for m in matches for s in m.matched_skills}
    return StaffingResult(matches=matches, uncovered_skills=sorted(set(req.required_skills) - covered)).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Shared: every dragon records its vote through this validated tool
# ---------------------------------------------------------------------------
@guided_tool
def record_dragon_verdict(
    dragon: str, decision: str, confidence: float, rationale: str, conditions: list[str], tool_context: ToolContext
) -> dict[str, Any]:
    """Record this dragon's formal vote on the deal (call exactly once, at the end of your review).

    Args:
        dragon: Your dragon id: `scope_dragon`, `pricing_dragon`, `swimlane_dragon` or `delivery_risk_dragon`.
        decision: `IN`, `IN_WITH_CONDITIONS` or `OUT`.
        confidence: 0.0-1.0 confidence in your decision.
        rationale: 20-1500 chars citing the tool evidence (numbers, ids) behind the vote.
        conditions: Conditions that must be met for an `IN_WITH_CONDITIONS` vote (empty list otherwise).

    Returns:
        dict: `{"status": "recorded", "verdict": DragonVerdict}` or a guided `ToolError`.
    """
    verdict = DragonVerdict.model_validate(
        {"dragon": dragon, "decision": decision, "confidence": confidence, "rationale": rationale, "conditions": conditions}
    )
    if verdict.decision.value == "IN_WITH_CONDITIONS" and not verdict.conditions:
        raise DealDragonsToolError(
            "MISSING_CONDITIONS",
            "IN_WITH_CONDITIONS requires at least one condition.",
            "Either list the concrete conditions (e.g. 'VP approval for 20% discount') or change decision to IN.",
        )
    votes = dict(tool_context.state.get("dragon_votes", {}))
    votes[verdict.dragon.value] = verdict.model_dump(mode="json")
    tool_context.state["dragon_votes"] = votes
    return {"status": "recorded", "verdict": verdict.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# High-stakes actions (wrapped with Human-in-the-Loop confirmation in hitl.py)
# ---------------------------------------------------------------------------
def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}-" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:10].upper()


@guided_tool
def grant_sow_technical_approval(
    deal_id: str, approved_price_usd: float, conditions: list[str], tool_context: ToolContext
) -> dict[str, Any]:
    """HIGH-STAKES: grant the Security practice's SOW technical approval for a deal.

    Requires explicit human confirmation (ADK tool confirmation). Only call after
    the Board verdict recommends `GRANT_TECHNICAL_APPROVAL`.

    Args:
        deal_id: Deal id `DEAL-YYYY-NNN`.
        approved_price_usd: Final approved total contract value in USD.
        conditions: Mandatory conditions attached to the approval.

    Returns:
        dict: `TechnicalApprovalResult` with an `approval_id`, or a guided `ToolError`.
    """
    req = TechnicalApprovalRequest.model_validate(
        {"deal_id": deal_id, "approved_price_usd": approved_price_usd, "conditions": conditions}
    )
    verdict = tool_context.state.get("board_verdict") or {}
    if verdict and verdict.get("next_action") != "GRANT_TECHNICAL_APPROVAL":
        raise DealDragonsToolError(
            "BOARD_DID_NOT_APPROVE",
            f"The Board recommended {verdict.get('next_action')}, not approval.",
            "Do not grant approval. Explain the Board's mandatory conditions to the user and offer a re-review.",
        )
    approval = TechnicalApprovalResult(
        deal_id=req.deal_id,
        approval_id=_stable_id("APR", req.deal_id, str(req.approved_price_usd)),
        approved_price_usd=req.approved_price_usd,
        conditions=req.conditions,
    )
    tool_context.state[f"approval:{req.deal_id}"] = approval.model_dump(mode="json")
    return approval.model_dump(mode="json")


@guided_tool
def soft_book_consultants(
    deal_id: str, consultant_ids: list[str], start_date: str, weeks: int, tool_context: ToolContext
) -> dict[str, Any]:
    """HIGH-STAKES: soft-book consultants onto a deal in the staffing system.

    Requires explicit human confirmation (ADK tool confirmation).

    Args:
        deal_id: Deal id `DEAL-YYYY-NNN`.
        consultant_ids: Consultant ids from `find_available_consultants`, e.g. `["C-103"]`.
        start_date: Booking start date `YYYY-MM-DD`.
        weeks: Booking length in weeks.

    Returns:
        dict: `SoftBookingResult` with `booking_ids`, or a guided `ToolError`.
    """
    req = SoftBookingRequest.model_validate(
        {"deal_id": deal_id, "consultant_ids": consultant_ids, "start_date": start_date, "weeks": weeks}
    )
    known = {c["consultant_id"] for c in catalog.consultants()}
    unknown = [c for c in req.consultant_ids if c not in known]
    if unknown:
        raise DealDragonsToolError(
            "UNKNOWN_CONSULTANTS",
            f"Consultants {unknown} are not on the bench.",
            "Call `find_available_consultants` and use only the returned `consultant_id` values.",
            valid_examples=sorted(known)[:4],
        )
    result = SoftBookingResult(
        deal_id=req.deal_id, booking_ids=[_stable_id("BKG", req.deal_id, c, req.start_date) for c in req.consultant_ids]
    )
    tool_context.state[f"booking:{req.deal_id}"] = result.model_dump(mode="json")
    return result.model_dump(mode="json")
