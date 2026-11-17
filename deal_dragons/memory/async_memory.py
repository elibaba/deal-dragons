"""Non-blocking memory generation & consolidation.

Memory Bank generation (LLM extraction + consolidation of facts such as
"Customer X always pushes for 20% discounts") takes seconds. Running it inline
would block the user's response, so the root agent's `after_agent_callback`
schedules it as a background `asyncio` task and returns immediately.
"""

from __future__ import annotations

import asyncio
import logging

from google.adk.agents.callback_context import CallbackContext

logger = logging.getLogger(__name__)

# Strong references so background tasks are not garbage-collected mid-flight.
_background_tasks: set[asyncio.Task] = set()


async def _consolidate_memory(callback_context: CallbackContext, invocation_id: str) -> None:
    try:
        await callback_context.add_session_to_memory()
        logger.info("memory_consolidated", extra={"invocation_id": invocation_id})
    except ValueError:
        logger.debug("memory_service_not_configured")
    except Exception as exc:  # noqa: BLE001 - never crash the serving path
        logger.warning("memory_consolidation_failed", extra={"invocation_id": invocation_id, "error_type": type(exc).__name__})


async def schedule_memory_consolidation(callback_context: CallbackContext) -> None:
    """after_agent_callback: fire-and-forget Memory Bank generation (does not block the UI)."""
    if callback_context.state.get("temp:guardrail_blocked"):
        return None  # never memorize blocked / malicious turns
    task = asyncio.create_task(
        _consolidate_memory(callback_context, callback_context.invocation_id),
        name=f"memory-consolidation-{callback_context.invocation_id}",
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    logger.info("memory_consolidation_scheduled", extra={"invocation_id": callback_context.invocation_id})
    return None


def pending_memory_tasks() -> int:
    """Number of in-flight background memory tasks (used by tests/health checks)."""
    return len(_background_tasks)
