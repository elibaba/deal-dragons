"""Central configuration for Deal Dragons.

All runtime settings are injected through environment variables (12-factor).
Secrets are NEVER read from source code: see `deal_dragons.infrastructure.secrets`
for the Google Cloud Secret Manager integration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Typed, immutable runtime settings."""

    # --- Google Cloud ------------------------------------------------------
    project_id: str = field(default_factory=lambda: os.environ.get("GOOGLE_CLOUD_PROJECT", ""))
    location: str = field(default_factory=lambda: os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"))
    agent_engine_id: str = field(default_factory=lambda: os.environ.get("AGENT_ENGINE_ID", ""))

    # --- Strategic model routing -----------------------------------------
    # Flash: high-volume, latency-sensitive specialist work (the dragons, intake, critic).
    fast_model: str = field(default_factory=lambda: os.environ.get("FAST_MODEL", "gemini-3.5-flash"))
    # Pro: deep multi-signal synthesis (the Board Chair verdict, mega-deals).
    pro_model: str = field(default_factory=lambda: os.environ.get("PRO_MODEL", "gemini-3.1-pro-preview"))
    # Summarizer used by ADK event compaction (cheap + fast).
    compaction_model: str = field(default_factory=lambda: os.environ.get("COMPACTION_MODEL", "gemini-3.5-flash"))

    # --- Persistence -------------------------------------------------------
    # Local default = SQLite file (persistent across restarts). Production = Agent Engine sessions.
    session_db_url: str = field(
        default_factory=lambda: os.environ.get("SESSION_DB_URL", "sqlite+aiosqlite:///./.deal_dragons_sessions.db")
    )

    # --- Guardrails / privacy ---------------------------------------------
    enable_cloud_dlp: bool = field(default_factory=lambda: _env_bool("ENABLE_CLOUD_DLP"))
    model_armor_template: str = field(default_factory=lambda: os.environ.get("MODEL_ARMOR_TEMPLATE", ""))

    # --- Observability -----------------------------------------------------
    enable_cloud_trace: bool = field(default_factory=lambda: _env_bool("ENABLE_CLOUD_TRACE"))
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))

    # --- Secret names (values live in Secret Manager, never in code) ------
    crm_token_secret_id: str = field(default_factory=lambda: os.environ.get("CRM_TOKEN_SECRET_ID", "deal-dragons-crm-token"))
    gemini_api_key_secret_id: str = field(
        default_factory=lambda: os.environ.get("GEMINI_API_KEY_SECRET_ID", "deal-dragons-gemini-api-key")
    )

    @property
    def use_agent_engine(self) -> bool:
        return bool(self.project_id and self.agent_engine_id)


settings = Settings()
