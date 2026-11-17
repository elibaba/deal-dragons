"""Guided error handling for tools.

Tools never raise into the agent loop. Instead they return a `ToolError`
envelope that tells the LLM *what went wrong* and *exactly how to recover*
(which tool to call, which argument format to use, valid examples).
"""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from deal_dragons.schemas import ToolError

logger = logging.getLogger(__name__)


class DealDragonsToolError(Exception):
    """Domain error carrying LLM-facing recovery guidance."""

    def __init__(
        self,
        error_code: str,
        message: str,
        recovery_instructions: str,
        valid_examples: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.recovery_instructions = recovery_instructions
        self.valid_examples = valid_examples or []

    def to_dict(self) -> dict[str, Any]:
        return ToolError(
            error_code=self.error_code,
            message=self.message,
            recovery_instructions=self.recovery_instructions,
            valid_examples=self.valid_examples,
        ).model_dump(mode="json")


def validation_error_to_tool_error(tool_name: str, exc: ValidationError) -> dict[str, Any]:
    """Convert a Pydantic ValidationError into actionable LLM guidance."""
    problems = [
        f"{'.'.join(str(p) for p in err['loc']) or 'input'}: {err['msg']}" for err in exc.errors()[:6]
    ]
    return ToolError(
        error_code="INVALID_ARGUMENTS",
        message=f"`{tool_name}` rejected the arguments: " + "; ".join(problems),
        recovery_instructions=(
            f"Fix ONLY the listed fields and call `{tool_name}` again. Do not invent values: "
            "if a value is unknown, call `fetch_deal_brief` or `lookup_security_offerings` first, "
            "or ask the user for it."
        ),
    ).model_dump(mode="json")


def guided_tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: converts any exception into a guided `ToolError` dict.

    Preserves the wrapped function's signature and docstring so that ADK can
    still generate the function declaration (JSON schema) for the LLM.
    """
    name = func.__name__

    def _handle(exc: Exception) -> dict[str, Any]:
        if isinstance(exc, DealDragonsToolError):
            logger.warning("tool_guided_error", extra={"tool": name, "error_code": exc.error_code})
            return exc.to_dict()
        if isinstance(exc, ValidationError):
            logger.warning("tool_validation_error", extra={"tool": name})
            return validation_error_to_tool_error(name, exc)
        logger.exception("tool_unexpected_error", extra={"tool": name})
        return ToolError(
            error_code="INTERNAL_TOOL_FAILURE",
            message=f"`{name}` failed unexpectedly ({type(exc).__name__}).",
            recovery_instructions=(
                "Retry once with the same arguments. If it fails again, continue the review "
                "without this data, state clearly that it is missing, and lower your confidence."
            ),
        ).model_dump(mode="json")

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                return _handle(exc)

        return async_wrapper

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            return _handle(exc)

    return wrapper
