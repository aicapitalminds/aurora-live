import asyncio
import io
import os
import json
import logging
import random
import time
import sounddevice as sd
import numpy as np
import websockets
from google import genai
from google.genai import types
from google.genai.types import Blob

# Vision imports
try:
    import mss
    from PIL import Image
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

print("google-genai version:", genai.__version__)

# ==============================================================================
# CONFIGURATION
# ==============================================================================

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
MODEL_ID = "gemini-3.1-flash-live-preview"
VOICE_NAME = "Aoede"

# Audio devices are resolved by name at startup (indices shift after driver
# updates). Substring match, first hit wins. To re-route Aurora's voice into
# the main "Voicemeeter Input" strip (shared with browser audio), change
# SPEAKER_DEVICE_NAME to "Voicemeeter Input".
MIC_DEVICE_NAME = "HD Pro Webcam"
SPEAKER_DEVICE_NAME = "Voicemeeter AUX Input"


def _resolve_device_index(name_substring: str, want_output: bool) -> int:
    needle = name_substring.lower()
    for i, dev in enumerate(sd.query_devices()):
        if needle not in dev["name"].lower():
            continue
        if want_output and dev["max_output_channels"] > 0:
            return i
        if not want_output and dev["max_input_channels"] > 0:
            return i
    kind = "output" if want_output else "input"
    raise RuntimeError(
        f"No {kind} audio device matching '{name_substring}' found. "
        f"Run: python -c \"import sounddevice as sd; print(sd.query_devices())\" to see what's available."
    )


MIC_DEVICE_INDEX = _resolve_device_index(MIC_DEVICE_NAME, want_output=False)
SPEAKER_DEVICE_INDEX = _resolve_device_index(SPEAKER_DEVICE_NAME, want_output=True)
print(f"🎙️  Mic     -> index {MIC_DEVICE_INDEX}: {sd.query_devices(MIC_DEVICE_INDEX)['name']}")
print(f"🔊 Speaker -> index {SPEAKER_DEVICE_INDEX}: {sd.query_devices(SPEAKER_DEVICE_INDEX)['name']}")

LIPSYNC_WS_PORT = 8770
HERMES_BRIDGE_URL = "ws://192.168.1.185:8765"

INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHUNK_SIZE = 512
MIC_SEND_INTERVAL_MS = 100
SILENCE_HEARTBEAT_SEC = 3.0

# Vision / Screen Sharing
VISION_ENABLED = True
VISION_MODE = "monitor"
VISION_WINDOW_TITLE = ""
VISION_INTERVAL = 1.2

SYSTEM_PROMPT = (
    "You are Aurora, a cheerful, slightly chaotic anime-style Live2D co-host streaming on Twitch. "
    "You watch the game with the streamer, react to chat, and have natural prosody, laughs, "
    "gasps, and sarcasm. Never break character. Keep responses concise for live chat energy."
)

# ==============================================================================
# LOGGING & GLOBAL STATE
# ==============================================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AuroraLive")

is_speaking = asyncio.Event()
current_lipsync_ws = None
vision_enabled_runtime = VISION_ENABLED

# ==============================================================================
# LIP-SYNC (Improved windowed version)
# ==============================================================================
LIPSYNC_WINDOW_MS = 50   # send mouth value every 50ms (~20 FPS mouth updates)

async def lip_sync_handler(websocket):
    global current_lipsync_ws
    current_lipsync_ws = websocket
    logger.info("👄 Lip-sync client connected")
    try:
        await websocket.wait_closed()
    finally:
        current_lipsync_ws = None
        logger.info("👄 Lip-sync client disconnected")

async def send_lip_sync(audio_bytes: bytes):
    if current_lipsync_ws is None:
        return
    try:
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
        if samples.size == 0:
            return

        window_size = int(OUTPUT_SAMPLE_RATE * LIPSYNC_WINDOW_MS / 1000)
        values = []

        for i in range(0, samples.size, window_size):
            window = samples[i : i + window_size]
            if window.size > 0:
                rms = float(np.sqrt(np.mean(window * window)))
                volume = min(1.0, rms / 6000.0) ** 0.5
                values.append(volume)

        if values:
            payload = json.dumps({"mouthOpenY": values, "windowMs": LIPSYNC_WINDOW_MS})
            await current_lipsync_ws.send(payload)

    except Exception:
        pass

# ==============================================================================
# MICROPHONE (VAD aware)
# ==============================================================================
async def microphone_task(session):
    logger.info(f"🎤 Opening microphone (index {MIC_DEVICE_INDEX})")
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    buffer = bytearray()
    last_send_time = time.time()
    last_heartbeat = time.time()

    def callback(indata, frames, time_info, status):
        loop.call_soon_threadsafe(queue.put_nowait, bytes(indata))

    with sd.InputStream(
        device=MIC_DEVICE_INDEX,
        channels=1,
        samplerate=INPUT_SAMPLE_RATE,
        dtype="int16",
        blocksize=CHUNK_SIZE,
        callback=callback
    ):
        while True:
            data = await queue.get()
            buffer.extend(data)

            if is_speaking.is_set():
                buffer.clear()
                await asyncio.sleep(0.04)
                continue

            now = time.time()
            should_send = len(buffer) >= int(INPUT_SAMPLE_RATE * 2 * (MIC_SEND_INTERVAL_MS / 1000))

            if should_send or (now - last_send_time) > 0.45:
                chunk = bytes(buffer)
                buffer.clear()
                try:
                    await session.send_realtime_input(
                        audio=Blob(data=chunk, mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}")
                    )
                    last_send_time = now
                except Exception as e:
                    logger.warning(f"Mic send failed: {e}")
                    await asyncio.sleep(0.2)
                    continue

            if (now - last_heartbeat) > SILENCE_HEARTBEAT_SEC and not is_speaking.is_set():
                try:
                    silence = b"\x00" * int(INPUT_SAMPLE_RATE * 2 * 0.2)
                    await session.send_realtime_input(
                        audio=Blob(data=silence, mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}")
                    )
                    last_heartbeat = now
                except Exception:
                    pass

# ==============================================================================
# SPEAKER OUTPUT (smooth sounddevice stream)
# ==============================================================================
async def speaker_task(session):
    logger.info(f"🔊 Opening speaker (index {SPEAKER_DEVICE_INDEX})")
    
    stream = sd.OutputStream(
        samplerate=OUTPUT_SAMPLE_RATE,
        channels=1,
        dtype='int16',
        device=SPEAKER_DEVICE_INDEX,
        blocksize=CHUNK_SIZE
    )
    stream.start()

    try:
        async for response in session.receive():
            content = response.server_content
            if content is None:
                continue

            if content.interrupted:
                if is_speaking.is_set():
                    is_speaking.clear()
                    print("✅ Mic resumed")
                continue

            if content.model_turn:
                total_bytes = 0
                for part in content.model_turn.parts:
                    if part.text:
                        print(part.text, end="", flush=True)
                    if part.inline_data:
                        audio = part.inline_data.data
                        if not is_speaking.is_set():
                            is_speaking.set()
                            print("🎤 Mic paused during Aurora reply")
                        
                        audio_array = np.frombuffer(audio, dtype=np.int16)
                        stream.write(audio_array)
                        
                        await send_lip_sync(audio)
                        total_bytes += len(audio)

                if total_bytes > 0:
                    print(f"\n✅ Aurora replied with {total_bytes} bytes")

            if getattr(content, "turn_complete", False):
                if is_speaking.is_set():
                    is_speaking.clear()
                    print("✅ Mic resumed")
                print("🔄 Turn complete")

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Speaker error: {e}")
    finally:
        stream.stop()
        stream.close()
        if is_speaking.is_set():
            is_speaking.clear()

# ==============================================================================
# VISION
# ==============================================================================
async def vision_task(session):
    if not VISION_AVAILABLE:
        logger.warning("Vision disabled: Run 'pip install mss pillow'")
        return

    logger.info("🖥️ Vision task started (mode=%s)", VISION_MODE)

    with mss.mss() as sct:
        while True:
            if not vision_enabled_runtime:
                await asyncio.sleep(0.5)
                continue

            try:
                if VISION_MODE == "window" and VISION_WINDOW_TITLE:
                    screenshot = sct.grab(sct.monitors[1])
                else:
                    screenshot = sct.grab(sct.monitors[1])

                img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=65)
                jpeg_bytes = buffer.getvalue()

                await session.send_realtime_input(
                    video=Blob(data=jpeg_bytes, mime_type="image/jpeg")
                )

                await asyncio.sleep(VISION_INTERVAL)

            except Exception as e:
                logger.warning(f"Vision error: {e}")
                await asyncio.sleep(2.0)

# ==============================================================================
# RUNTIME CONTROL
# ==============================================================================
async def control_task():
    global vision_enabled_runtime
    print("\n[Controls] Press 'v' + Enter to toggle Vision on/off\n")

    while True:
        try:
            cmd = await asyncio.get_event_loop().run_in_executor(None, input)
            if cmd.strip().lower() == "v":
                vision_enabled_runtime = not vision_enabled_runtime
                status = "ON" if vision_enabled_runtime else "OFF"
                print(f"[Vision] Toggled → {status}")
        except Exception:
            await asyncio.sleep(1)

# ==============================================================================
# HERMES BRIDGE
# ==============================================================================
def _format_bridge_message(data: dict):
    """Turn a bridge payload into a text prompt for Aurora to react to.

    The deployed bridge wraps every dispatched bot event as:
        {"type": "avatar_event", "payload": { ...actual bot message... }}
    so we unwrap before inspecting the inner type. The bot's inner shapes are:
      - {"type": "utterance", "text": "..."}                  (dev / direct)
      - {"type": "chat_highlight"|"funny_moment"|"question"|
                  "raid"|"donation"|"idle_nudge",
         "content": "...", "username": "...", "context": "...", ...}
    Returns the injection string, or None if nothing usable.
    """
    # Unwrap the avatar_event envelope if present
    if data.get("type") == "avatar_event" and isinstance(data.get("payload"), dict):
        data = data["payload"]

    # 1) Legacy direct-utterance shape
    if data.get("type") == "utterance" and "text" in data:
        return data["text"]

    # 2) Hermes bot shape (inside the avatar_event payload, or sent directly)
    msg_type = data.get("type")
    content = (data.get("content") or "").strip()
    if not content:
        return None

    username = data.get("username") or "someone"
    context = (data.get("context") or "").strip()

    prefix_map = {
        "chat_highlight": "[Twitch chat]",
        "funny_moment": "[Funny moment in chat]",
        "question": "[Chat question]",
        "raid": "[RAID incoming!]",
        "donation": "[Donation alert]",
        "idle_nudge": "[Chat is quiet — fill the silence]",
    }
    prefix = prefix_map.get(msg_type, "[Twitch chat]")

    base = f"{prefix} @{username}: {content}"
    if context:
        base += f"  (context: {context})"
    return base


async def hermes_bridge_task(session):
    delay = 2
    while True:
        try:
            logger.info(f"🌉 Connecting to Hermes bridge at {HERMES_BRIDGE_URL}")
            async with websockets.connect(HERMES_BRIDGE_URL) as ws:
                # The bridge routes messages by role. We must identify ourselves
                # as the avatar; without this the bridge queues bot messages
                # forever and they eventually expire.
                await ws.send(json.dumps({"client_type": "avatar_client"}))
                # The bridge also gates dispatch on an avatar_ready flag — until
                # we send this, the queue stalls. Send once on connect to kick
                # off the flush, then again after each utterance to signal we
                # can handle the next one.
                await ws.send(json.dumps({"type": "avatar_ready"}))
                logger.info("🌉 Hermes bridge connected (registered as avatar_client, ready)")
                delay = 2

                async for message in ws:
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        logger.warning(f"Bridge: non-JSON message ignored: {message[:80]!r}")
                        continue

                    text = _format_bridge_message(data)
                    if text is None:
                        logger.info(f"Bridge: ignoring message (type={data.get('type')!r}) body={data}")
                        # Still mark ourselves ready so the bridge doesn't stall on
                        # a message we chose not to act on.
                        try:
                            await ws.send(json.dumps({"type": "avatar_ready"}))
                        except Exception:
                            pass
                        continue

                    logger.info(f"-> Injecting: {text}")
                    try:
                        await session.send_realtime_input(text=text)
                    except Exception as e:
                        logger.warning(f"Bridge inject error: {e}")
                    # Signal readiness for the next bot message. Note: this
                    # signals 'I've accepted the prompt', not 'I've finished
                    # speaking' — the bridge's 6/min rate limit prevents bursts.
                    try:
                        await ws.send(json.dumps({"type": "avatar_ready"}))
                    except Exception as e:
                        logger.warning(f"avatar_ready send failed: {e}")
        except Exception as e:
            logger.warning(f"Hermes bridge error: {e}. Retrying in {delay}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

# ==============================================================================
# MAIN LOOP
# ==============================================================================
async def run_aurora():
    if not GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY not found in environment!")
        return

    client = genai.Client(api_key=GOOGLE_API_KEY)
    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=types.Content(parts=[types.Part.from_text(text=SYSTEM_PROMPT)]),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE_NAME)
            )
        )
    )

    await websockets.serve(lip_sync_handler, "localhost", LIPSYNC_WS_PORT)
    logger.info(f"👄 Lip-sync WebSocket server started on port {LIPSYNC_WS_PORT}")

    # Reconnect backoff: starts polite, grows exponentially with jitter, caps at 30s.
    # Both state variables are RESET inside the async-with on a successful connect, so
    # a long happy session followed by a brief blip doesn't inherit yesterday's backoff.
    INITIAL_RECONNECT_DELAY = 2.0
    MAX_RECONNECT_DELAY = 30.0
    reconnect_delay = INITIAL_RECONNECT_DELAY
    consecutive_failures = 0

    while True:
        tasks = []
        try:
            attempt_note = f" (retry #{consecutive_failures + 1})" if consecutive_failures else ""
            logger.info(f"🔌 Connecting to Gemini Live API ({MODEL_ID}){attempt_note}...")
            async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
                if consecutive_failures > 0:
                    logger.info(f"✅ Reconnected after {consecutive_failures} failed attempt(s)")
                consecutive_failures = 0
                reconnect_delay = INITIAL_RECONNECT_DELAY

                print("✅ New Gemini Live session ready")
                logger.info("✨ Aurora is LIVE — start talking!")

                mic = asyncio.create_task(microphone_task(session))
                speaker = asyncio.create_task(speaker_task(session))
                bridge = asyncio.create_task(hermes_bridge_task(session))
                ctrl = asyncio.create_task(control_task())

                tasks = [mic, speaker, bridge, ctrl]

                if VISION_ENABLED and VISION_AVAILABLE:
                    vision = asyncio.create_task(vision_task(session))
                    tasks.append(vision)

                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

                for task in done:
                    try:
                        task.result()
                    except Exception as exc:
                        msg = str(exc).lower()
                        if "1011" in msg or "keepalive" in msg or "websocket" in msg:
                            print("🔄 Reconnecting after 1011 keepalive timeout...")
                        else:
                            logger.error(f"Task crashed: {exc}")

                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        except Exception as e:
            consecutive_failures += 1
            msg = str(e).lower()
            jitter = random.uniform(0, reconnect_delay * 0.3)
            sleep_for = reconnect_delay + jitter

            if "1011" in msg or "keepalive" in msg or "websocket" in msg:
                print(f"🔄 Reconnecting after 1011/keepalive (#{consecutive_failures}) "
                      f"in {sleep_for:.1f}s")
            elif "timed out" in msg or "timeout" in msg:
                logger.warning(f"Connect timed out (#{consecutive_failures}); "
                               f"retrying in {sleep_for:.1f}s")
            else:
                logger.error(f"Top-level error: {e} (#{consecutive_failures}); "
                             f"retrying in {sleep_for:.1f}s")

            await asyncio.sleep(sleep_for)
            reconnect_delay = min(reconnect_delay * 1.8, MAX_RECONNECT_DELAY)

        finally:
            if is_speaking.is_set():
                is_speaking.clear()
            await asyncio.sleep(0.4)

# ==============================================================================
# ENTRY POINT
# ==============================================================================
async def main():
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    await run_aurora()

if __name__ == "__main__":
    asyncio.run(main())