"""Optional Google Cloud Model Armor integration.

When `MODEL_ARMOR_TEMPLATE` is set (e.g.
`projects/<p>/locations/us-central1/templates/deal-dragons`), user prompts and
model responses are screened for prompt injection / jailbreak, malicious URLs,
sensitive data and RAI violations by Model Armor. The template itself is
provisioned by Terraform (`terraform/security.tf`).
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass

from deal_dragons.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ArmorVerdict:
    blocked: bool
    reason: str = ""


@functools.lru_cache(maxsize=1)
def _client():  # pragma: no cover - requires GCP
    from google.api_core.client_options import ClientOptions
    from google.cloud import modelarmor_v1

    return modelarmor_v1.ModelArmorClient(
        client_options=ClientOptions(api_endpoint=f"modelarmor.{settings.location}.rep.googleapis.com")
    )


def screen_prompt(text: str) -> ArmorVerdict:
    """Screen a user prompt with Model Armor. Fails open (logged) if the API is unavailable."""
    if not settings.model_armor_template or not text:
        return ArmorVerdict(blocked=False)
    try:  # pragma: no cover - requires GCP
        from google.cloud import modelarmor_v1

        resp = _client().sanitize_user_prompt(
            request=modelarmor_v1.SanitizeUserPromptRequest(
                name=settings.model_armor_template, user_prompt_data=modelarmor_v1.DataItem(text=text)
            )
        )
        match = resp.sanitization_result.filter_match_state == modelarmor_v1.FilterMatchState.MATCH_FOUND
        return ArmorVerdict(blocked=match, reason="model_armor_match" if match else "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("model_armor_unavailable", extra={"error_type": type(exc).__name__})
        return ArmorVerdict(blocked=False)
