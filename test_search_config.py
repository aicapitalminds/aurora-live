"""One-shot probe: which Live tool configs does the model accept?

Run:  .venv\\Scripts\\python.exe test_search_config.py
Tries three configs and prints the exact accept/reject reason for each,
so we know whether google_search itself or the search+functions mix
kills the handshake on this model.
"""
import asyncio
import os
import re
import traceback
from pathlib import Path


def load_api_key() -> str | None:
    """Env var first, else parse it out of start-aurora.bat."""
    key = os.environ.get("GOOGLE_API_KEY")
    if key:
        return key
    bat = Path(__file__).parent / "start-aurora.bat"
    if bat.exists():
        m = re.search(r'set\s+"GOOGLE_API_KEY=([^"]+)"', bat.read_text(encoding="utf-8"))
        if m and "YOUR_GOOGLE" not in m.group(1):
            return m.group(1)
    return None

from google import genai
from google.genai import types

MODEL_ID = "gemini-3.1-flash-live-preview"

FUNC_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="get_weather",
            description="Get current weather for a location.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"location": types.Schema(type=types.Type.STRING)},
                required=["location"],
            ),
        )
    ]
)
SEARCH_TOOL = types.Tool(google_search=types.GoogleSearch())

CASES = [
    ("functions only (baseline)", [FUNC_TOOL]),
    ("google_search only", [SEARCH_TOOL]),
    ("google_search + functions", [SEARCH_TOOL, FUNC_TOOL]),
]


async def try_case(client, label, tools):
    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        tools=tools,
    )
    try:
        async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
            # Handshake succeeded; poke it once to be sure the session is real.
            await session.send_realtime_input(text="ping")
            try:
                await asyncio.wait_for(anext(session.receive().__aiter__()), timeout=10)
            except (StopAsyncIteration, asyncio.TimeoutError):
                pass
        print(f"[OK]   {label}")
    except Exception as e:
        print(f"[FAIL] {label}\n       {type(e).__name__}: {e}")
        tb = traceback.format_exc().strip().splitlines()
        print("       last frames: " + " | ".join(tb[-3:]))


async def main():
    key = load_api_key()
    if not key:
        print("GOOGLE_API_KEY not found in env or start-aurora.bat")
        return
    client = genai.Client(api_key=key)
    print("google-genai:", genai.__version__, "| model:", MODEL_ID)
    for label, tools in CASES:
        await try_case(client, label, tools)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        input("\nDone — press Enter to close...")
