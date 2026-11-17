"""Structured JSON logging (Cloud Logging compatible).

Every record is emitted as one JSON object with `severity`, `message`,
`logging.googleapis.com/trace` (so Cloud Logging links logs to Cloud Trace
spans), and any `extra={...}` metadata. All values pass through the PII
redactor before they are written.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace

from deal_dragons.config import settings
from deal_dragons.observability.pii import redact_obj, redact_text_regex

_RESERVED = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as single-line, PII-scrubbed JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": redact_text_regex(record.getMessage()),
            "module": record.module,
            "function": record.funcName,
        }
        span_ctx = trace.get_current_span().get_span_context()
        if span_ctx and span_ctx.is_valid:
            trace_id = format(span_ctx.trace_id, "032x")
            payload["trace_id"] = trace_id
            payload["span_id"] = format(span_ctx.span_id, "016x")
            if settings.project_id:
                payload["logging.googleapis.com/trace"] = f"projects/{settings.project_id}/traces/{trace_id}"
                payload["logging.googleapis.com/spanId"] = payload["span_id"]
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED and not k.startswith("_")}
        if extras:
            payload["labels"] = redact_obj(extras)
        if record.exc_info:
            payload["exception"] = redact_text_regex(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


_configured = False


def configure_logging() -> None:
    """Install the JSON formatter on the root logger (idempotent)."""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
    for noisy in ("httpx", "httpcore", "urllib3", "google.auth"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True
