"""Secure secret management via Google Cloud Secret Manager.

Design rules (enforced by `tests/test_secrets.py`):
  * No API keys, tokens or passwords are hardcoded anywhere in the repo.
  * In production (Cloud Run) the service account reads secrets from Secret
    Manager at runtime, or Cloud Run injects them as env vars via
    `secret_key_ref` (see `terraform/cloud_run.tf`).
  * Locally, developers may export the env var themselves; we never write it.
  * Values are cached in-process (LRU) and never logged.
"""

from __future__ import annotations

import functools
import logging
import os

from deal_dragons.config import settings

logger = logging.getLogger(__name__)


class SecretUnavailableError(RuntimeError):
    """Raised when a secret cannot be resolved from env or Secret Manager."""


@functools.lru_cache(maxsize=32)
def _access_secret_manager(project_id: str, secret_id: str, version: str = "latest") -> str:
    # Imported lazily so unit tests do not need GCP credentials.
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")


def get_secret(secret_id: str, *, env_fallback: str | None = None, required: bool = True) -> str | None:
    """Resolve a secret value securely.

    Resolution order:
      1. An env var injected by the platform (Cloud Run `secret_key_ref`).
      2. Google Cloud Secret Manager (`projects/<p>/secrets/<secret_id>`).

    Args:
        secret_id: Secret Manager secret id, e.g. `deal-dragons-crm-token`.
        env_fallback: Optional env var name that the platform may inject.
        required: Raise `SecretUnavailableError` if not found.

    Returns:
        The secret value, or None when `required=False` and it is missing.
    """
    if env_fallback and os.environ.get(env_fallback):
        return os.environ[env_fallback]
    if settings.project_id:
        try:
            value = _access_secret_manager(settings.project_id, secret_id)
            logger.info("secret_resolved", extra={"secret_id": secret_id, "source": "secret_manager"})
            return value
        except Exception as exc:  # noqa: BLE001 - surface as typed error below
            logger.warning(
                "secret_manager_lookup_failed",
                extra={"secret_id": secret_id, "error_type": type(exc).__name__},
            )
    if required:
        raise SecretUnavailableError(
            f"Secret '{secret_id}' not found. Create it with: "
            f"gcloud secrets create {secret_id} --data-file=- (see README#secrets)."
        )
    return None


def configure_model_credentials() -> None:
    """Wire Gemini credentials without hardcoding keys.

    Production uses Vertex AI with the Cloud Run service account (ADC), which
    needs no key at all. Only when Vertex is disabled do we fetch an AI Studio
    key from Secret Manager and expose it to the google-genai client.
    """
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() in {"1", "true"}
    if use_vertex or os.environ.get("GOOGLE_API_KEY"):
        return
    key = get_secret(settings.gemini_api_key_secret_id, required=False)
    if key:
        os.environ["GOOGLE_API_KEY"] = key
