"""Distributed tracing with OpenTelemetry -> Google Cloud Trace.

ADK already emits OTel spans for `invoke_agent`, `call_llm` and `execute_tool`.
We register a TracerProvider (Cloud Trace exporter in prod, console/no-op
locally) so those spans, our custom tool spans (`tool.*`) and the
intent/outcome plugin spans all share one trace id from user query to answer.
"""

from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from deal_dragons.config import settings

logger = logging.getLogger(__name__)
_initialized = False


def configure_tracing(service_name: str = "deal-dragons") -> TracerProvider | None:
    """Configure the global OTel TracerProvider once (idempotent)."""
    global _initialized
    if _initialized:
        return None
    provider = TracerProvider(resource=Resource.create({"service.name": service_name, "gcp.project_id": settings.project_id}))
    if settings.enable_cloud_trace and settings.project_id:
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter(project_id=settings.project_id)))
            logger.info("cloud_trace_enabled", extra={"project_id": settings.project_id})
        except Exception as exc:  # noqa: BLE001
            logger.warning("cloud_trace_exporter_unavailable", extra={"error_type": type(exc).__name__})
    try:
        trace.set_tracer_provider(provider)
    except Exception:  # noqa: BLE001 - provider already set by ADK server (--trace_to_cloud)
        pass
    _initialized = True
    return provider


def get_tracer(name: str = "deal_dragons") -> trace.Tracer:
    return trace.get_tracer(name)
