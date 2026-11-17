"""Memory pipeline: PII redaction before persistence + non-blocking async consolidation."""

import asyncio
from types import SimpleNamespace

from google.adk.events.event import Event
from google.adk.memory import InMemoryMemoryService
from google.adk.sessions.session import Session
from google.genai import types

from deal_dragons.memory import async_memory
from deal_dragons.memory.context_management import build_context_cache_config, build_events_compaction_config
from deal_dragons.memory.services import RedactingMemoryService


def test_memory_service_redacts_before_storage():
    inner = InMemoryMemoryService()
    svc = RedactingMemoryService(inner)
    ev = Event(author="user", content=types.Content(role="user", parts=[types.Part(text="CFO email cfo@helvetia.example")]))
    session = Session(id="s1", app_name="deal_dragons", user_id="u1", events=[ev])
    asyncio.run(svc.add_session_to_memory(session))
    res = asyncio.run(svc.search_memory(app_name="deal_dragons", user_id="u1", query="email"))
    texts = " ".join(p.text for m in res.memories for p in m.content.parts if p.text)
    assert "cfo@helvetia.example" not in texts
    assert "[REDACTED:EMAIL_ADDRESS]" in texts


def test_async_consolidation_does_not_block():
    started = asyncio.Event()

    class SlowCtx(SimpleNamespace):
        async def add_session_to_memory(self):
            started.set()
            await asyncio.sleep(0.5)

    async def run():
        ctx = SlowCtx(state={}, invocation_id="inv-1")
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        await async_memory.schedule_memory_consolidation(ctx)
        elapsed = loop.time() - t0
        assert elapsed < 0.1  # returned immediately
        assert async_memory.pending_memory_tasks() == 1
        await asyncio.wait_for(started.wait(), 1)
        await asyncio.sleep(0.6)
        assert async_memory.pending_memory_tasks() == 0

    asyncio.run(run())


def test_blocked_turns_are_not_memorized():
    ctx = SimpleNamespace(state={"temp:guardrail_blocked": True}, invocation_id="inv-2")
    asyncio.run(async_memory.schedule_memory_consolidation(ctx))
    assert async_memory.pending_memory_tasks() == 0


def test_compaction_and_cache_configs():
    c = build_events_compaction_config()
    assert c.token_threshold and c.event_retention_size and c.compaction_interval
    assert build_context_cache_config().ttl_seconds == 1800
