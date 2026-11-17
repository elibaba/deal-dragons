"""Human-in-the-Loop hooks for high-stakes actions.

ADK `FunctionTool(require_confirmation=...)` pauses the run and emits a
`adk_request_confirmation` event; the tool only executes after a human
explicitly approves it in the UI / API (the app is resumable, so the run
continues from the exact pause point).

  * `grant_sow_technical_approval` - ALWAYS requires confirmation.
  * `soft_book_consultants`        - requires confirmation when booking more
    than one consultant or more than 4 weeks (conditional predicate).
"""

from __future__ import annotations

from google.adk.tools import FunctionTool

from deal_dragons.tools.deal_tools import grant_sow_technical_approval, soft_book_consultants


def booking_needs_human_approval(deal_id: str = "", consultant_ids: list[str] | None = None, weeks: int = 0, **_: object) -> bool:
    """Predicate: soft-bookings of >1 consultant or >4 weeks need a human sign-off."""
    return len(consultant_ids or []) > 1 or int(weeks or 0) > 4


technical_approval_tool = FunctionTool(grant_sow_technical_approval, require_confirmation=True)
soft_booking_tool = FunctionTool(soft_book_consultants, require_confirmation=booking_needs_human_approval)
