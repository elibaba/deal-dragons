"""Intent-vs-outcome capture as an ADK plugin.

For every agent, model call and tool call we log TWO structured events:
  * `intent`  - BEFORE execution: who is about to do what, with which args.
  * `outcome` - AFTER execution: what actually happened (status, latency, error).
Both carry the same `correlation_id` and the active OTel trace id, so a
reviewer can diff "what the agent meant to do" against "what it did".
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from opentelemetry import trace

from deal_dragons.observability.pii import redact_obj

logger = logging.getLogger("deal_dragons.audit")


def _span_attrs(**attrs: Any) -> None:
    span = trace.get_current_span()
    for k, v in attrs.items():
        if v is not None:
            span.set_attribute(f"deal_dragons.{k}", str(v)[:500])


class IntentOutcomeLoggingPlugin(BasePlugin):
    """Logs structured intent (before) and outcome (after) records for agents, LLM calls and tools."""

    def __init__(self) -> None:
        super().__init__(name="intent_outcome_logging")
        self._starts: dict[str, tuple[str, float]] = {}

    # ---- agents ------------------------------------------------------------
    async def before_agent_callback(self, *, agent: BaseAgent, callback_context: CallbackContext) -> None:
        key = f"agent:{callback_context.invocation_id}:{agent.name}"
        cid = uuid.uuid4().hex[:12]
        self._starts[key] = (cid, time.perf_counter())
        logger.info("intent", extra={"event": "intent", "kind": "agent", "agent": agent.name,
                                     "correlation_id": cid, "invocation_id": callback_context.invocation_id,
                                     "planned_action": agent.description})
        _span_attrs(intent=f"run agent {agent.name}")
        return None

    async def after_agent_callback(self, *, agent: BaseAgent, callback_context: CallbackContext) -> None:
        key = f"agent:{callback_context.invocation_id}:{agent.name}"
        cid, t0 = self._starts.pop(key, ("unknown", time.perf_counter()))
        logger.info("outcome", extra={"event": "outcome", "kind": "agent", "agent": agent.name, "correlation_id": cid,
                                      "status": "completed", "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                                      "state_keys": sorted(k for k in callback_context.state.to_dict().keys())[:30]})
        return None

    # ---- model -------------------------------------------------------------
    async def before_model_callback(self, *, callback_context: CallbackContext, llm_request: LlmRequest) -> LlmResponse | None:
        key = f"model:{callback_context.invocation_id}:{callback_context.agent_name}"
        cid = uuid.uuid4().hex[:12]
        self._starts[key] = (cid, time.perf_counter())
        logger.info("intent", extra={"event": "intent", "kind": "llm_call", "agent": callback_context.agent_name,
                                     "model": llm_request.model, "correlation_id": cid,
                                     "tools_offered": sorted(llm_request.tools_dict.keys())})
        return None

    async def after_model_callback(self, *, callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None:
        key = f"model:{callback_context.invocation_id}:{callback_context.agent_name}"
        cid, t0 = self._starts.pop(key, ("unknown", time.perf_counter()))
        usage = llm_response.usage_metadata
        calls = [p.function_call.name for p in (llm_response.content.parts if llm_response.content else []) if p.function_call]
        logger.info("outcome", extra={"event": "outcome", "kind": "llm_call", "agent": callback_context.agent_name,
                                      "correlation_id": cid, "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                                      "function_calls": calls, "error_code": llm_response.error_code,
                                      "prompt_tokens": getattr(usage, "prompt_token_count", None),
                                      "output_tokens": getattr(usage, "candidates_token_count", None)})
        return None

    # ---- tools -------------------------------------------------------------
    async def before_tool_callback(self, *, tool: BaseTool, tool_args: dict[str, Any], tool_context: ToolContext) -> dict | None:
        key = f"tool:{tool_context.function_call_id}"
        cid = uuid.uuid4().hex[:12]
        self._starts[key] = (cid, time.perf_counter())
        logger.info("intent", extra={"event": "intent", "kind": "tool", "tool": tool.name, "agent": tool_context.agent_name,
                                     "correlation_id": cid, "tool_args": redact_obj(tool_args)})
        _span_attrs(intent=f"call {tool.name}")
        return None

    async def after_tool_callback(self, *, tool: BaseTool, tool_args: dict[str, Any], tool_context: ToolContext, result: dict) -> dict | None:
        key = f"tool:{tool_context.function_call_id}"
        cid, t0 = self._starts.pop(key, ("unknown", time.perf_counter()))
        status = result.get("status", "success") if isinstance(result, dict) else "success"
        logger.info("outcome", extra={"event": "outcome", "kind": "tool", "tool": tool.name, "agent": tool_context.agent_name,
                                      "correlation_id": cid, "status": status,
                                      "error_code": result.get("error_code") if isinstance(result, dict) else None,
                                      "latency_ms": round((time.perf_counter() - t0) * 1000, 1)})
        _span_attrs(outcome=f"{tool.name}:{status}")
        return None

    async def on_tool_error_callback(self, *, tool: BaseTool, tool_args: dict[str, Any], tool_context: ToolContext, error: Exception) -> dict | None:
        key = f"tool:{tool_context.function_call_id}"
        cid, t0 = self._starts.pop(key, ("unknown", time.perf_counter()))
        logger.error("outcome", extra={"event": "outcome", "kind": "tool", "tool": tool.name, "correlation_id": cid,
                                       "status": "exception", "error_type": type(error).__name__,
                                       "latency_ms": round((time.perf_counter() - t0) * 1000, 1)})
        # Guided recovery instead of crashing the run.
        return {"status": "error", "error_code": "TOOL_EXCEPTION",
                "message": f"{tool.name} raised {type(error).__name__}.",
                "recovery_instructions": "Retry once; if it fails again, proceed without this data and say so."}
