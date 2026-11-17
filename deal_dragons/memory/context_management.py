"""History compaction and context caching (context-bloat management).

* `EventsCompactionConfig` (token-based + sliding window): once a session's
  prompt reaches `token_threshold` tokens, ADK summarizes older events with a
  cheap Flash summarizer and keeps only the last `event_retention_size` raw
  events. A sliding-window trigger (`compaction_interval` / `overlap_size`)
  also compacts every N invocations so long negotiation sessions stay small.
* `ContextCacheConfig`: the large, static Board constitution + catalog prefix
  is cached on Vertex AI (Gemini context caching) to cut latency and cost.
"""

from __future__ import annotations

from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps.app import EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.models import Gemini

from deal_dragons.config import settings

COMPACTION_TOKEN_THRESHOLD = 24_000
COMPACTION_EVENT_RETENTION = 6
COMPACTION_INTERVAL_INVOCATIONS = 5
COMPACTION_OVERLAP = 1


def build_events_compaction_config() -> EventsCompactionConfig:
    """Token-based + sliding-window history compaction with a Flash summarizer."""
    return EventsCompactionConfig(
        token_threshold=COMPACTION_TOKEN_THRESHOLD,
        event_retention_size=COMPACTION_EVENT_RETENTION,
        compaction_interval=COMPACTION_INTERVAL_INVOCATIONS,
        overlap_size=COMPACTION_OVERLAP,
        summarizer=LlmEventSummarizer(llm=Gemini(model=settings.compaction_model)),
    )


def build_context_cache_config() -> ContextCacheConfig:
    """Gemini context caching for the static constitution/catalog prefix."""
    return ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10)
