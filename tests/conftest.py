import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "")

import pytest  # noqa: E402


class FakeToolContext:
    """Minimal stand-in for ADK ToolContext (only `.state` is used by our tools)."""

    def __init__(self, state=None):
        self.state = dict(state or {})
        self.agent_name = "test_agent"
        self.function_call_id = "fc-test"
        self.invocation_id = "inv-test"


@pytest.fixture
def tool_context():
    return FakeToolContext()
