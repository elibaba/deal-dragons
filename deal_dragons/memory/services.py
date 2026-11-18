"""Persistent session + long-term memory service factories.

| Environment | Sessions                                   | Long-term memory                          |
|-------------|--------------------------------------------|-------------------------------------------|
| Production  | `VertexAiSessionService` (Agent Engine)    | `VertexAiMemoryBankService` (Memory Bank) |
| Local dev   | `DatabaseSessionService` (SQLite/Postgres) | `InMemoryMemoryService`                   |

`RedactingMemoryService` wraps whichever memory backend is active and scrubs
PII from every event BEFORE it is persisted (memory pipeline redaction).
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from google.adk.events.event import Event
from google.adk.memory import BaseMemoryService, InMemoryMemoryService, VertexAiMemoryBankService
from google.adk.memory.base_memory_service import SearchMemoryResponse
from google.adk.sessions import BaseSessionService, DatabaseSessionService, VertexAiSessionService
from google.adk.sessions.session import Session

from deal_dragons.config import settings
from deal_dragons.observability.pii import redact_text

logger = logging.getLogger(__name__)


def _redact_event(event: Event) -> Event:
    clone = copy.deepcopy(event)
    if clone.content and clone.content.parts:
        for part in clone.content.parts:
            if part.text:
                part.text = redact_text(part.text)
    return clone


class RedactingMemoryService(BaseMemoryService):
    """Decorator that redacts PII from session events before they reach long-term memory."""

    def __init__(self, inner: BaseMemoryService) -> None:
        self._inner = inner

    async def add_session_to_memory(self, session: Session) -> None:
        clean = session.model_copy(update={"events": [_redact_event(e) for e in session.events]})
        await self._inner.add_session_to_memory(clean)

    async def add_events_to_memory(
        self, *, app_name: str, user_id: str, events: Sequence[Event],
        session_id: str | None = None, custom_metadata: Mapping[str, object] | None = None,
    ) -> None:
        await self._inner.add_events_to_memory(
            app_name=app_name, user_id=user_id, events=[_redact_event(e) for e in events],
            session_id=session_id, custom_metadata=custom_metadata,
        )

    async def search_memory(self, *, app_name: str, user_id: str, query: str) -> SearchMemoryResponse:
        return await self._inner.search_memory(app_name=app_name, user_id=user_id, query=query)


def build_session_service() -> BaseSessionService:
    """Persistent session store: Agent Engine Sessions in prod, SQL database locally."""
    if settings.use_agent_engine:
        logger.info("session_service", extra={"backend": "vertex_ai_agent_engine"})
        return VertexAiSessionService(
            project=settings.project_id, location=settings.region, agent_engine_id=settings.agent_engine_id
        )
    logger.info("session_service", extra={"backend": "database", "url_scheme": settings.session_db_url.split(":")[0]})
    return DatabaseSessionService(db_url=settings.session_db_url)


def build_memory_service() -> BaseMemoryService:
    """Long-term memory: Vertex AI Memory Bank in prod, in-memory locally - always PII-redacted."""
    inner: BaseMemoryService
    if settings.use_agent_engine:
        inner = VertexAiMemoryBankService(
            project=settings.project_id, location=settings.region, agent_engine_id=settings.agent_engine_id
        )
    else:
        inner = InMemoryMemoryService()
    return RedactingMemoryService(inner)


def service_uris() -> dict[str, Any]:
    """URIs consumed by `get_fast_api_app` (adk api_server) for the same backends."""
    if settings.use_agent_engine:
        uri = f"agentengine://projects/{settings.project_id}/locations/{settings.region}/reasoningEngines/{settings.agent_engine_id}"
        return {"session_service_uri": uri, "memory_service_uri": uri}
    return {"session_service_uri": settings.session_db_url, "memory_service_uri": None}
