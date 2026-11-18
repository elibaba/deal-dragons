"""Production entrypoint (Cloud Run): ADK FastAPI server with persistent services + Cloud Trace."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from google.adk.cli.fast_api import get_fast_api_app

from deal_dragons.config import settings
from deal_dragons.memory.services import service_uris
from deal_dragons.observability.logging_setup import configure_logging

configure_logging()

AGENTS_DIR = str(Path(__file__).resolve().parent)
uris = service_uris()

app = get_fast_api_app(
    agents_dir=AGENTS_DIR,
    session_service_uri=uris["session_service_uri"],
    memory_service_uri=uris["memory_service_uri"],
    web=os.environ.get("SERVE_WEB_UI", "true").lower() == "true",
    trace_to_cloud=settings.enable_cloud_trace,
    allow_origins=[o for o in os.environ.get("ALLOW_ORIGINS", "").split(",") if o],
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8080")),
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
