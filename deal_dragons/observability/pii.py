"""PII redaction used by BOTH the logging pipeline and the memory pipeline.

Two layers:
  1. Fast, deterministic regex scrubbing (always on, zero network calls).
  2. Google Cloud Sensitive Data Protection (Cloud DLP) `deidentify_content`
     when `ENABLE_CLOUD_DLP=true` - catches names, addresses and other
     infoTypes regexes cannot.

The redactor is applied:
  * in `StructuredJsonFormatter` before any log line is written;
  * in `RedactingMemoryService` before session events are sent to Memory Bank;
  * in `DealGuardrailPlugin.before_model_callback` before prompts leave the process.
"""

from __future__ import annotations

import functools
import logging
import re
from typing import Any

from deal_dragons.config import settings

logger = logging.getLogger(__name__)

# Ordered: most specific first.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL_ADDRESS", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("CREDIT_CARD_NUMBER", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("IBAN_CODE", re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}\b")),
    ("GCP_API_KEY", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("BEARER_TOKEN", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{20,}=*")),
    ("PHONE_NUMBER", re.compile(r"(?<!\w)\+?\d{1,3}[ .-]?\(?\d{2,4}\)?[ .-]?\d{3,4}[ .-]?\d{3,4}(?!\w)")),
    ("US_SOCIAL_SECURITY_NUMBER", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
]

DLP_INFO_TYPES = ["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD_NUMBER", "IBAN_CODE", "PERSON_NAME", "STREET_ADDRESS"]


def redact_text_regex(text: str) -> str:
    """Replace PII matches with `[REDACTED:<INFO_TYPE>]` placeholders."""
    if not text:
        return text
    for label, pattern in _PATTERNS:
        text = pattern.sub(f"[REDACTED:{label}]", text)
    return text


@functools.lru_cache(maxsize=1)
def _dlp_client():  # pragma: no cover - requires GCP
    from google.cloud import dlp_v2

    return dlp_v2.DlpServiceClient()


def redact_text_cloud_dlp(text: str) -> str:  # pragma: no cover - requires GCP
    """De-identify text with Cloud DLP, replacing findings with their infoType name."""
    client = _dlp_client()
    response = client.deidentify_content(
        request={
            "parent": f"projects/{settings.project_id}/locations/global",
            "inspect_config": {"info_types": [{"name": n} for n in DLP_INFO_TYPES]},
            "deidentify_config": {
                "info_type_transformations": {
                    "transformations": [{"primitive_transformation": {"replace_with_info_type_config": {}}}]
                }
            },
            "item": {"value": text},
        }
    )
    return response.item.value


def redact_text(text: str) -> str:
    """Redact PII: regex always, then Cloud DLP when enabled (fails open to regex result)."""
    scrubbed = redact_text_regex(text)
    if settings.enable_cloud_dlp and settings.project_id and scrubbed:
        try:
            return redact_text_cloud_dlp(scrubbed)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cloud_dlp_unavailable", extra={"error_type": type(exc).__name__})
    return scrubbed


def redact_obj(obj: Any) -> Any:
    """Recursively redact strings inside dicts/lists (for structured log payloads)."""
    if isinstance(obj, str):
        return redact_text_regex(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_obj(v) for v in obj]
    return obj
