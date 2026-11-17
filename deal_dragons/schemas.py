"""Explicit Pydantic JSON schemas for every tool input/output and agent output.

These models are the contract between the LLM and our code:
  * Tool functions validate their raw arguments with `*Request.model_validate`
    and reject anything off-contract with a guided, recoverable error.
  * Tool results are serialized through `*Result.model_dump(mode="json")` so the
    LLM always sees the same, documented shape.
  * The Board Chair agent is constrained with `output_schema=BoardVerdict`.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    """Base model: unknown fields are rejected, strings are trimmed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# Enums shared across tools
# ---------------------------------------------------------------------------
class Swimlane(str, Enum):
    PSO = "PSO"
    MANDIANT = "MANDIANT"
    WIZ = "WIZ"
    SECURITY_FDE = "SECURITY_FDE"


class DragonName(str, Enum):
    SCOPE = "scope_dragon"
    PRICING = "pricing_dragon"
    SWIMLANE = "swimlane_dragon"
    DELIVERY_RISK = "delivery_risk_dragon"


class Decision(str, Enum):
    IN = "IN"  # "I'm in"
    IN_WITH_CONDITIONS = "IN_WITH_CONDITIONS"
    OUT = "OUT"  # "I'm out"


Level = Literal["L4", "L5", "L6", "L7"]
DEAL_ID_PATTERN = r"^DEAL-\d{4}-\d{3}$"
OFFERING_ID_PATTERN = r"^OFF-[A-Z0-9\-]+$"


# ---------------------------------------------------------------------------
# Deal brief (intake)
# ---------------------------------------------------------------------------
class DealBrief(StrictModel):
    deal_id: str = Field(pattern=DEAL_ID_PATTERN, description="CRM deal id, e.g. DEAL-2026-001")
    customer: str = Field(min_length=2, max_length=120)
    industry: str
    region: Literal["EMEA", "MENAT", "NA", "JAPAC", "LATAM"]
    requested_offerings: list[str] = Field(min_length=1, max_length=8)
    proposed_price_usd: float = Field(gt=0, le=50_000_000)
    proposed_discount_pct: float = Field(ge=0, le=100)
    duration_weeks: int = Field(gt=0, le=104)
    notes: str = Field(default="", max_length=4000)

    @field_validator("requested_offerings")
    @classmethod
    def _offering_ids(cls, v: list[str]) -> list[str]:
        import re

        bad = [o for o in v if not re.match(OFFERING_ID_PATTERN, o)]
        if bad:
            raise ValueError(f"Invalid offering ids {bad}; expected format OFF-XXXX")
        return v


class FetchDealBriefRequest(StrictModel):
    deal_id: str = Field(pattern=DEAL_ID_PATTERN)


# ---------------------------------------------------------------------------
# Offering catalog
# ---------------------------------------------------------------------------
class OfferingLookupRequest(StrictModel):
    offering_ids: list[str] = Field(min_length=1, max_length=8)


class Offering(StrictModel):
    offering_id: str
    name: str
    category: str
    owning_swimlane: Swimlane
    typical_weeks: int
    typical_fte: float
    required_skills: list[str]
    description: str


class OfferingLookupResult(StrictModel):
    status: Literal["success"] = "success"
    offerings: list[Offering]
    unknown_offering_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------
class PriceQuoteRequest(StrictModel):
    offering_ids: list[str] = Field(min_length=1, max_length=8)
    duration_weeks: int = Field(gt=0, le=104)
    discount_pct: float = Field(ge=0, le=100)
    proposed_price_usd: float = Field(gt=0)


class PriceQuoteResult(StrictModel):
    status: Literal["success"] = "success"
    list_price_usd: float
    discounted_price_usd: float
    proposed_price_usd: float
    estimated_cost_usd: float
    gross_margin_pct: float
    effort_person_days: float
    price_gap_pct: float = Field(description="(proposed - discounted list) / discounted list * 100")


class GuardrailCheckRequest(StrictModel):
    deal_value_usd: float = Field(gt=0)
    discount_pct: float = Field(ge=0, le=100)
    gross_margin_pct: float = Field(ge=-100, le=100)


class PolicyViolation(StrictModel):
    rule: str
    severity: Literal["BLOCKER", "WARNING"]
    message: str
    remediation: str


class GuardrailCheckResult(StrictModel):
    status: Literal["success"] = "success"
    passed: bool
    violations: list[PolicyViolation]


# ---------------------------------------------------------------------------
# Swimlanes
# ---------------------------------------------------------------------------
class SwimlaneRequest(StrictModel):
    offering_ids: list[str] = Field(min_length=1, max_length=8)
    deal_notes: str = Field(default="", max_length=4000)


class SwimlaneAssignment(StrictModel):
    offering_id: str
    owner: Swimlane
    pso_can_sell: bool


class SwimlaneResult(StrictModel):
    status: Literal["success"] = "success"
    assignments: list[SwimlaneAssignment]
    conflicts: list[str]
    recommended_split: str


# ---------------------------------------------------------------------------
# Staffing
# ---------------------------------------------------------------------------
class StaffingRequest(StrictModel):
    required_skills: list[str] = Field(min_length=1, max_length=12)
    region: Literal["EMEA", "MENAT", "NA", "JAPAC", "LATAM"]
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    max_utilization_pct: int = Field(default=80, ge=0, le=100)


class ConsultantMatch(StrictModel):
    consultant_id: str
    alias: str
    level: Level
    matched_skills: list[str]
    utilization_pct: int
    available_from: str


class StaffingResult(StrictModel):
    status: Literal["success"] = "success"
    matches: list[ConsultantMatch]
    uncovered_skills: list[str]


# ---------------------------------------------------------------------------
# Dragon verdicts (each dragon records one through a validated tool)
# ---------------------------------------------------------------------------
class DragonVerdict(StrictModel):
    dragon: DragonName
    decision: Decision
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=20, max_length=1500)
    conditions: list[str] = Field(default_factory=list, max_length=8)


# ---------------------------------------------------------------------------
# Board verdict (Chair output_schema)
# ---------------------------------------------------------------------------
class BoardVerdict(StrictModel):
    deal_id: str = Field(pattern=DEAL_ID_PATTERN)
    final_decision: Decision
    headline: str = Field(max_length=200, description="One-line Dragons' Den style verdict")
    dragon_votes: dict[str, Decision]
    mandatory_conditions: list[str] = Field(default_factory=list)
    recommended_price_usd: float = Field(ge=0)
    recommended_staffing: list[str] = Field(default_factory=list, description="consultant_ids")
    swimlane_split: str
    next_action: Literal["GRANT_TECHNICAL_APPROVAL", "REWORK_AND_RESUBMIT", "DECLINE"]


# ---------------------------------------------------------------------------
# High-stakes HITL actions
# ---------------------------------------------------------------------------
class TechnicalApprovalRequest(StrictModel):
    deal_id: str = Field(pattern=DEAL_ID_PATTERN)
    approved_price_usd: float = Field(gt=0)
    conditions: list[str] = Field(default_factory=list)


class TechnicalApprovalResult(StrictModel):
    status: Literal["approved"] = "approved"
    deal_id: str
    approval_id: str
    approved_price_usd: float
    conditions: list[str]


class SoftBookingRequest(StrictModel):
    deal_id: str = Field(pattern=DEAL_ID_PATTERN)
    consultant_ids: list[str] = Field(min_length=1, max_length=10)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    weeks: int = Field(gt=0, le=104)


class SoftBookingResult(StrictModel):
    status: Literal["soft_booked"] = "soft_booked"
    deal_id: str
    booking_ids: list[str]


# ---------------------------------------------------------------------------
# Uniform error envelope returned to the LLM (guided recovery)
# ---------------------------------------------------------------------------
class ToolError(StrictModel):
    status: Literal["error"] = "error"
    error_code: str
    message: str
    recovery_instructions: str
    valid_examples: list[str] = Field(default_factory=list)
