"""Terminal demo: run a full Deal Review Board session, including the HITL approval pause.

    python scripts/demo_review.py DEAL-2026-003
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.adk.runners import Runner  # noqa: E402
from google.genai import types  # noqa: E402

from deal_dragons.agent import app  # noqa: E402
from deal_dragons.memory.services import build_memory_service, build_session_service  # noqa: E402


async def main(deal_id: str) -> None:
    runner = Runner(app=app, session_service=build_session_service(), memory_service=build_memory_service())
    session = await runner.session_service.create_session(app_name=app.name, user_id="demo")

    async def send(content: types.Content) -> list:
        pending = []
        async for event in runner.run_async(user_id="demo", session_id=session.id, new_message=content):
            for call in event.get_function_calls() or []:
                if call.name == "adk_request_confirmation":
                    pending.append(call)
                else:
                    print(f"  [{event.author}] -> tool {call.name}({json.dumps(call.args)[:120]})")
            if event.content and event.content.parts and event.is_final_response():
                text = "".join(p.text or "" for p in event.content.parts)
                if text.strip():
                    print(f"\n[{event.author}] {text}\n")
        return pending

    await send(types.Content(role="user", parts=[types.Part(text=f"Please run a full board review of {deal_id}.")]))
    pending = await send(types.Content(role="user", parts=[types.Part(text="The board said yes - grant the SOW technical approval.")]))
    for call in pending:
        answer = input(f"\nHUMAN CHECKPOINT {call.args.get('toolConfirmation', {}).get('hint', '')}\nApprove? [y/N] ")
        await send(types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
            id=call.id, name="adk_request_confirmation", response={"confirmed": answer.strip().lower() == "y"}))]))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "DEAL-2026-003"))
