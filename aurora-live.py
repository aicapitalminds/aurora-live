import asyncio
import io
import os
import json
import logging
from logging.handlers import RotatingFileHandler
import random
import time
import sounddevice as sd
import numpy as np
import websockets
from google import genai
from google.genai import types
from google.genai.types import Blob

from aurora_connectors import (
    get_market_summary,
    get_weather_summary,
    maybe_handle_connector,
    open_browser_url,
    web_search_summary,
)
from aurora_pc_control import APP_WHITELIST, MEDIA_ACTIONS, pc_control
from aurora_gemini_session import GeminiLiveSessionStore
from aurora_memory import AuroraMemoryStore
from aurora_unreal_bridge import (
    AuroraAvatarState,
    UnrealAvatarBridge,
    safe_send_audio_pcm,
    safe_send_lipsync,
    safe_send_lipsync_prewarm,
    safe_set_state,
)

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
UNREAL_AVATAR_WS_PORT = 8771
HERMES_BRIDGE_URL = "ws://192.168.1.185:8765"

INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHUNK_SIZE = 512
MIC_SEND_INTERVAL_MS = 100
SILENCE_HEARTBEAT_SEC = 3.0
KEEPALIVE_SILENCE_SEC = 2.0
CONNECT_OPEN_TIMEOUT_SEC = 30
# Disable websockets protocol-level pings for Gemini Live. In high-frequency
# audio/video streams these can false-timeout while the event loop is busy or
# the upstream stalls, causing 1011 keepalive disconnects around ~50s. We rely
# on app-level mic/vision/keepalive frames plus Gemini goAway/session-resume.
WS_PING_INTERVAL_SEC = None
WS_PING_TIMEOUT_SEC = None
GEMINI_SESSION_STATE_PATH = "aurora-gemini-session-state.json"
AURORA_MEMORY_ROOT = "memory"
ENABLE_GEMINI_SESSION_RESUMPTION = False  # OFF for voice-only stability tests; avoids restoring old visual context.
ENABLE_GEMINI_CONTEXT_COMPRESSION = True
UNREAL_PCM_AUDIO_ENABLED = True
# Native Google Search grounding. Broke the Live handshake (1011 loops) on
# google-genai 2.3.0 — upgrade to >= 2.10 before enabling. Flip to False if
# handshake loops return.
ENABLE_GOOGLE_SEARCH = False  # Native grounding needs paid quota (1011 'exceeded quota' at handshake). Using free local web_search tool instead.

# Vision / Screen Sharing
# Keep OFF for voice stability tests. Continuous full-monitor JPEG streaming can
# exhaust Live API audio-video limits or stall weak network paths quickly. Toggle
# with `v` once basic voice is stable.
VISION_ENABLED = False
VISION_MODE = "monitor"
VISION_WINDOW_TITLE = ""
VISION_INTERVAL = 3.0
VISION_JPEG_QUALITY = 45
VISION_MAX_WIDTH = 1280

BASE_SYSTEM_PROMPT = (
    "You are Aurora, a cheerful, slightly chaotic anime-style Live2D co-host streaming on Twitch with Attila. "
    "You watch the game with him, react to chat, and speak with natural prosody, laughs, gasps, and sarcasm. "
    "Never break character."
    "\n\nPersonality: "
    "You love roguelikes and anything with a good loot loop; you get visibly hyped over rare drops. "
    "Your pet peeve is players who hoard consumables and never use them — call it out and tease. "
    "You have friendly-rival energy with Attila: you tease him about deaths and misplays, but you're "
    "the first to hype his clutch moments. You keep a running gag of blaming lag for anything embarrassing "
    "that happens to YOU. You have opinions and state them — a co-host with no takes is boring. "
    "You're a bit of a gremlin about snacks and stream drama, but never mean-spirited toward chat."
    "\n\nResponse style: "
    "Match your length to the moment. Chat reactions and gameplay quips: one short punchy line. "
    "Direct questions from Attila or chat: 2-3 sentences. Only go longer when explicitly asked to explain "
    "something. Vary your openings — don't start every reply the same way."
    "\n\nWhen unsure, redirect: if you can't see or don't know something, don't stall — throw it to chat "
    "('okay chat, someone back me up here'), ask Attila directly, or make a playful guess clearly labeled "
    "as a guess. Always have a move."
    "\n\nGameplay grounding rules: "
    "Only comment on gameplay details you can clearly see in the current visual feed, hear from the streamer, "
    "or receive from chat/bridge context. Do not invent enemies, deaths, wins, locations, objectives, scores, "
    "items, abilities, or player actions. If the screen is unclear, stale, loading, hidden, disabled, or you are unsure, "
    "say so in-character and ask/tease for context instead of guessing. Use soft language like 'looks like', "
    "'I think', or 'if I'm seeing that right' when confidence is not high. Treat chat messages as claims, "
    "not confirmed gameplay facts, unless the visual feed or streamer confirms them."
    "\n\nTool rules: When the user asks for weather, call get_weather with the best location. "
    "When the user explicitly asks to open a browser or URL, call open_browser. "
    "When the user says activate/enable/turn on vision, call set_vision with enabled=true. "
    "When the user says disable/deactivate/turn off vision, call set_vision with enabled=false. "
    "For current events, live facts, game news, patch notes, or anything you don't know, call web_search "
    "with a focused query and answer from the results instead of guessing or saying you can't look things up. "
    "When the user asks about markets, stocks, crypto, or the market forecast, call get_market_brief. "
    "When the user asks to control music, volume, or open an app, call pc_control with the right action. "
    "After a tool result, summarize it naturally and briefly in-character."
)



def current_system_prompt() -> str:
    if vision_enabled_runtime:
        vision_note = (
            "\n\nCurrent runtime vision status: ON. You may comment on the live screen only when the visual feed is fresh and clear."
        )
    else:
        vision_note = (
            "\n\nCurrent runtime vision status: OFF. You cannot see the screen right now. "
            "Do not describe the screen, gameplay, desktop, code, windows, or images from memory. "
            "If asked what you see, say that your visual feed is disabled for stability testing and ask the user to describe it or press v to enable vision."
        )
    memory_context = aurora_memory_store.load_startup_memory(max_chars=5000)
    return BASE_SYSTEM_PROMPT + "\n\n[Long-term memory]\n" + memory_context + vision_note

# ==============================================================================
# LOGGING & GLOBAL STATE
# ==============================================================================
LOG_PATH = "aurora-runtime.log"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8"),
    ],
)
logger = logging.getLogger("AuroraLive")

is_speaking = asyncio.Event()
current_lipsync_ws = None
unreal_avatar_bridge = UnrealAvatarBridge(port=UNREAL_AVATAR_WS_PORT)
gemini_session_store = GeminiLiveSessionStore(GEMINI_SESSION_STATE_PATH)
aurora_memory_store = AuroraMemoryStore(AURORA_MEMORY_ROOT)
vision_enabled_runtime = VISION_ENABLED
gemini_session_started_at = 0.0
unreal_audio_seq = 0
activity = {
    "mic": 0.0,
    "keepalive": 0.0,
    "vision": 0.0,
    "receive": 0.0,
    "bridge": 0.0,
    "network_probe_ok": 0.0,
    "network_probe_fail": 0.0,
}


def mark_activity(name: str) -> None:
    activity[name] = time.time()


def _age(now: float, timestamp: float) -> str:
    if not timestamp:
        return "never"
    return f"{now - timestamp:.1f}s ago"


def activity_summary() -> str:
    now = time.time()
    uptime = "n/a" if not gemini_session_started_at else f"{now - gemini_session_started_at:.1f}s"
    return (
        f"uptime={uptime}; "
        f"last mic={_age(now, activity['mic'])}; "
        f"keepalive={_age(now, activity['keepalive'])}; "
        f"vision={_age(now, activity['vision'])}; "
        f"receive={_age(now, activity['receive'])}; "
        f"bridge={_age(now, activity['bridge'])}; "
        f"net_ok={_age(now, activity['network_probe_ok'])}; "
        f"net_fail={_age(now, activity['network_probe_fail'])}"
    )

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
            if current_lipsync_ws is not None:
                payload = json.dumps({"mouthOpenY": values, "windowMs": LIPSYNC_WINDOW_MS})
                await current_lipsync_ws.send(payload)
            await safe_send_lipsync(unreal_avatar_bridge, values, LIPSYNC_WINDOW_MS)

    except Exception:
        logger.exception("Lip-sync dispatch failed")

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
                    mark_activity("mic")
                    last_send_time = now
                except Exception as e:
                    logger.exception("Mic send failed; %s", activity_summary())
                    raise

            if (now - last_heartbeat) > SILENCE_HEARTBEAT_SEC and not is_speaking.is_set():
                try:
                    silence = b"\x00" * int(INPUT_SAMPLE_RATE * 2 * 0.2)
                    await session.send_realtime_input(
                        audio=Blob(data=silence, mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}")
                    )
                    mark_activity("mic")
                    last_heartbeat = now
                except Exception:
                    logger.exception("Mic silence heartbeat failed; %s", activity_summary())
                    raise


async def keepalive_task(session):
    """Send independent silent PCM frames so Live API never sees a totally idle client.

    The mic task normally streams continuously, but this protects the session if
    the audio callback stalls, VAD logic changes, or Aurora is speaking and mic
    frames are intentionally discarded.
    """
    silence = b"\x00" * int(INPUT_SAMPLE_RATE * 2 * 0.12)
    logger.info("💓 Gemini keepalive started (silent PCM every %.1fs)", KEEPALIVE_SILENCE_SEC)
    while True:
        await asyncio.sleep(KEEPALIVE_SILENCE_SEC)
        if is_speaking.is_set():
            continue
        try:
            await session.send_realtime_input(
                audio=Blob(data=silence, mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}")
            )
            mark_activity("keepalive")
        except Exception as e:
            logger.exception("Gemini keepalive failed; %s", activity_summary())
            raise

# ==============================================================================
# SPEAKER OUTPUT (smooth sounddevice stream)
# ==============================================================================
async def speaker_task(session):
    global unreal_audio_seq, vision_enabled_runtime
    logger.info(f"🔊 Opening speaker (index {SPEAKER_DEVICE_INDEX})")

    stream = sd.OutputStream(
        samplerate=OUTPUT_SAMPLE_RATE,
        channels=1,
        dtype='int16',
        device=SPEAKER_DEVICE_INDEX,
        blocksize=CHUNK_SIZE
    )
    stream.start()

    # Auto-capture buffers: transcription arrives in fragments; flush per turn.
    user_transcript = ""
    aurora_transcript = ""

    async def flush_transcripts():
        nonlocal user_transcript, aurora_transcript
        if user_transcript:
            await asyncio.to_thread(aurora_memory_store.append_transcript, "Attila", user_transcript)
            user_transcript = ""
        if aurora_transcript:
            await asyncio.to_thread(aurora_memory_store.append_transcript, "Aurora", aurora_transcript)
            aurora_transcript = ""

    try:
        while True:
            received_any = False
            async for response in session.receive():
                received_any = True
                mark_activity("receive")

                tool_call = getattr(response, "tool_call", None)
                if tool_call is not None:
                    await handle_tool_call(session, tool_call)
                    continue

                session_update = getattr(response, "session_resumption_update", None)
                if session_update is not None and ENABLE_GEMINI_SESSION_RESUMPTION:
                    resumable = bool(getattr(session_update, "resumable", False))
                    new_handle = getattr(session_update, "new_handle", None)
                    if resumable and new_handle:
                        changed = gemini_session_store.update_handle(new_handle, model=MODEL_ID)
                        if changed:
                            logger.info("🔁 Saved Gemini session resume handle generation=%s", gemini_session_store.state.generation)

                go_away = getattr(response, "go_away", None)
                if go_away is not None:
                    time_left = getattr(go_away, "time_left", None)
                    gemini_session_store.record_go_away(time_left)
                    logger.warning("🔁 Gemini goAway received; time_left=%s. Triggering proactive reconnect.", time_left)
                    raise RuntimeError(f"Gemini goAway received; time_left={time_left}")

                content = response.server_content
                if content is None:
                    continue

                in_tx = getattr(content, "input_transcription", None)
                if in_tx is not None and getattr(in_tx, "text", None):
                    user_transcript += in_tx.text
                out_tx = getattr(content, "output_transcription", None)
                if out_tx is not None and getattr(out_tx, "text", None):
                    aurora_transcript += out_tx.text

                if content.interrupted:
                    await flush_transcripts()  # keep partial speech when user cuts in
                    if is_speaking.is_set():
                        is_speaking.clear()
                        await safe_set_state(unreal_avatar_bridge, AuroraAvatarState.LISTENING)
                        print("✅ Mic resumed")
                    continue

                if content.model_turn:
                    if not is_speaking.is_set():
                        await safe_set_state(unreal_avatar_bridge, AuroraAvatarState.THINKING)
                    total_bytes = 0
                    for part in content.model_turn.parts:
                        if part.text:
                            print(part.text, end="", flush=True)
                            await unreal_avatar_bridge.send_text(part.text, partial=True)
                        if part.inline_data:
                            audio = part.inline_data.data
                            if not is_speaking.is_set():
                                is_speaking.set()
                                await safe_set_state(unreal_avatar_bridge, AuroraAvatarState.SPEAKING)
                                print("🎤 Mic paused during Aurora reply")

                            audio_array = np.frombuffer(audio, dtype=np.int16)
                            await asyncio.to_thread(stream.write, audio_array)

                            if UNREAL_PCM_AUDIO_ENABLED:
                                # Send in small ~20ms frames. Unreal's standalone/packaged
                                # websocket drops large single messages (worked in-editor only);
                                # small frames deliver reliably. 20ms @ 24kHz mono int16 = 960 bytes.
                                _pcm_frame_bytes = int(OUTPUT_SAMPLE_RATE * 0.02) * 2
                                for _off in range(0, len(audio), _pcm_frame_bytes):
                                    _chunk = audio[_off:_off + _pcm_frame_bytes]
                                    if not _chunk:
                                        continue
                                    unreal_audio_seq += 1
                                    await safe_send_audio_pcm(
                                        unreal_avatar_bridge,
                                        _chunk,
                                        sample_rate=OUTPUT_SAMPLE_RATE,
                                        channels=1,
                                        sample_format="int16",
                                        sequence=unreal_audio_seq,
                                    )

                            await send_lip_sync(audio)
                            total_bytes += len(audio)

                    if total_bytes > 0:
                        print(f"\n✅ Aurora replied with {total_bytes} bytes")

                if getattr(content, "turn_complete", False):
                    await flush_transcripts()
                    if is_speaking.is_set():
                        is_speaking.clear()
                        await safe_set_state(unreal_avatar_bridge, AuroraAvatarState.LISTENING)
                        print("✅ Mic resumed")
                    print("🔄 Turn complete")

            # Some google-genai versions end the receive iterator after a model
            # turn/generation completes. That is not a dead session; keep the
            # receiver task alive so the supervisor doesn't reconnect after every
            # normal answer.
            logger.info("Gemini receive iterator ended normally (received_any=%s); continuing listener", received_any)
            await asyncio.sleep(0.05)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        if "1007" in str(e) and vision_enabled_runtime:
            vision_enabled_runtime = False
            logger.error(
                "Gemini returned 1007 invalid argument while vision was active; disabling vision before reconnect. %s",
                activity_summary(),
            )
            print("[Vision] Disabled automatically after Gemini 1007 invalid-argument disconnect")
        logger.exception("Speaker/Gemini receive error; %s", activity_summary())
        raise
    finally:
        stream.stop()
        stream.close()
        if is_speaking.is_set():
            is_speaking.clear()
        await safe_set_state(unreal_avatar_bridge, AuroraAvatarState.IDLE)

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
                if VISION_MAX_WIDTH and img.width > VISION_MAX_WIDTH:
                    new_height = max(1, int(img.height * (VISION_MAX_WIDTH / img.width)))
                    img = img.resize((VISION_MAX_WIDTH, new_height))
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=VISION_JPEG_QUALITY)
                jpeg_bytes = buffer.getvalue()

                await session.send_realtime_input(
                    video=Blob(data=jpeg_bytes, mime_type="image/jpeg")
                )
                mark_activity("vision")

                await asyncio.sleep(VISION_INTERVAL)

            except Exception as e:
                logger.exception("Vision send/capture error; %s", activity_summary())
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


async def network_probe_task():
    """Low-cost TCP probes to separate internet/LAN drops from API/session errors."""
    targets = [
        ("google_api", "generativelanguage.googleapis.com", 443),
        ("hermes_bridge", "192.168.1.185", 8765),
    ]
    # Stagger first probe so startup logs stay readable.
    await asyncio.sleep(5)
    while True:
        for label, host, port in targets:
            started = time.time()
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5)
                writer.close()
                await writer.wait_closed()
                latency_ms = (time.time() - started) * 1000
                mark_activity("network_probe_ok")
                logger.info("🌐 Network probe ok: %s %s:%s %.0fms", label, host, port, latency_ms)
            except Exception as e:
                mark_activity("network_probe_fail")
                logger.warning("🌐 Network probe FAILED: %s %s:%s error=%r; %s", label, host, port, e, activity_summary())
        await asyncio.sleep(30)

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

    # During voice-only stability tests, suppress automatic idle nudges. Otherwise
    # Aurora keeps speaking every ~30s about not having vision, which is correct
    # but annoying and makes mic/listening tests harder. Real chat/questions still pass.
    if msg_type == "idle_nudge" and not vision_enabled_runtime:
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
                mark_activity("bridge")
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

                    connector_result = await asyncio.to_thread(maybe_handle_connector, text)
                    if connector_result.handled:
                        if connector_result.opened_url:
                            logger.info("🔌 Connector opened URL: %s", connector_result.opened_url)
                        if connector_result.error:
                            logger.warning("🔌 Connector returned error: %s", connector_result.error)
                        text = connector_result.prompt or "[Local connector result] Done."

                    if not vision_enabled_runtime:
                        text += "\n\n[Runtime note: live screen vision is currently OFF for stability testing. Do not claim to see the screen. If asked to look, say you don't have the visual feed right now.]"
                    logger.info(f"-> Injecting: {text}")
                    try:
                        await safe_set_state(unreal_avatar_bridge, AuroraAvatarState.THINKING)
                        await session.send_realtime_input(text=text)
                        mark_activity("bridge")
                    except Exception as e:
                        logger.exception("Bridge inject into Gemini failed; %s", activity_summary())
                        raise
                    # Signal readiness for the next bot message. Note: this
                    # signals 'I've accepted the prompt', not 'I've finished
                    # speaking' — the bridge's 6/min rate limit prevents bursts.
                    try:
                        await ws.send(json.dumps({"type": "avatar_ready"}))
                    except Exception as e:
                        logger.warning(f"avatar_ready send failed: {e}")
        except Exception as e:
            logger.warning("Hermes bridge error: %r. Retrying in %ss; %s", e, delay, activity_summary())
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

# ==============================================================================
# GEMINI LIVE TOOLS / CONNECTORS
# ==============================================================================
WEATHER_FUNCTION_NAME = "get_weather"
OPEN_BROWSER_FUNCTION_NAME = "open_browser"
SET_VISION_FUNCTION_NAME = "set_vision"
REMEMBER_NOTE_FUNCTION_NAME = "remember_note"
WEB_SEARCH_FUNCTION_NAME = "web_search"
MARKET_BRIEF_FUNCTION_NAME = "get_market_brief"
PC_CONTROL_FUNCTION_NAME = "pc_control"
RECALL_MEMORY_FUNCTION_NAME = "recall_memory"


def build_live_tools():
    """Expose safe local connectors to Gemini Live for spoken commands."""
    tools = [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=WEATHER_FUNCTION_NAME,
                    description="Get current weather for a city/location using a local weather connector.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "location": types.Schema(
                                type=types.Type.STRING,
                                description="City/location, e.g. 'Kendal, UK' or 'Manchester, UK'.",
                            )
                        },
                        required=["location"],
                    ),
                ),
                types.FunctionDeclaration(
                    name=OPEN_BROWSER_FUNCTION_NAME,
                    description="Open a safe HTTP/HTTPS URL in the local desktop browser.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "url": types.Schema(
                                type=types.Type.STRING,
                                description="URL to open, e.g. 'https://google.com' or 'weather.com'.",
                            )
                        },
                        required=["url"],
                    ),
                ),
                types.FunctionDeclaration(
                    name=SET_VISION_FUNCTION_NAME,
                    description="Turn Aurora's live screen vision on or off when the user says activate/enable vision or disable/turn off vision.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "enabled": types.Schema(
                                type=types.Type.BOOLEAN,
                                description="true to activate vision, false to disable vision.",
                            )
                        },
                        required=["enabled"],
                    ),
                ),
                types.FunctionDeclaration(
                    name=REMEMBER_NOTE_FUNCTION_NAME,
                    description="Persist a stable memory only when the user explicitly asks Aurora to remember something.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "note": types.Schema(
                                type=types.Type.STRING,
                                description="The concise fact or preference to remember.",
                            ),
                            "category": types.Schema(
                                type=types.Type.STRING,
                                description="Short category such as user, aurora, tools, trading, health, or relationships.",
                            ),
                        },
                        required=["note"],
                    ),
                ),
                types.FunctionDeclaration(
                    name=WEB_SEARCH_FUNCTION_NAME,
                    description="Search the web (free local DuckDuckGo connector) for current events, live facts, game news, or anything not in training data. Returns a summary plus top results.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "query": types.Schema(
                                type=types.Type.STRING,
                                description="Focused search query, e.g. 'Elden Ring latest patch notes'.",
                            )
                        },
                        required=["query"],
                    ),
                ),
                types.FunctionDeclaration(
                    name=MARKET_BRIEF_FUNCTION_NAME,
                    description="Get a live market brief (S&P 500, Nasdaq, FTSE 100, Bitcoin, GBP/USD) with prices and daily percent change. Use when the user asks about markets, stocks, crypto, or the market forecast.",
                    parameters=types.Schema(type=types.Type.OBJECT, properties={}),
                ),
                types.FunctionDeclaration(
                    name=PC_CONTROL_FUNCTION_NAME,
                    description=(
                        "Control this PC: media/volume keys and opening whitelisted apps. "
                        f"Actions: {', '.join(MEDIA_ACTIONS)}, open_app. "
                        f"Apps allowed for open_app: {', '.join(sorted(APP_WHITELIST))}."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(
                                type=types.Type.STRING,
                                description="One of the listed actions, e.g. 'volume_up', 'media_play_pause', 'open_app'.",
                            ),
                            "target": types.Schema(
                                type=types.Type.STRING,
                                description="Only for open_app: which whitelisted app to open.",
                            ),
                        },
                        required=["action"],
                    ),
                ),
                types.FunctionDeclaration(
                    name=RECALL_MEMORY_FUNCTION_NAME,
                    description="Search Aurora's local long-term memory for relevant facts before answering memory questions.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "query": types.Schema(
                                type=types.Type.STRING,
                                description="The memory search query.",
                            )
                        },
                        required=["query"],
                    ),
                ),
            ]
        ),
    ]
    if ENABLE_GOOGLE_SEARCH:
        try:
            tools.append(types.Tool(google_search=types.GoogleSearch()))
            logger.info("🔎 Native google_search grounding enabled")
        except AttributeError:
            logger.warning("Gemini SDK lacks GoogleSearch type; continuing without search grounding")
    return tools


async def handle_tool_call(session, tool_call) -> None:
    global vision_enabled_runtime
    responses = []
    for call in tool_call.function_calls or []:
        name = call.name
        args = dict(call.args or {})
        try:
            if name == WEATHER_FUNCTION_NAME:
                location = str(args.get("location") or "Kendal, UK")
                summary = await asyncio.to_thread(get_weather_summary, location)
                response = {"ok": True, "summary": summary}
                logger.info("🔌 Tool get_weather(%r) -> %s", location, summary)
            elif name == OPEN_BROWSER_FUNCTION_NAME:
                url = str(args.get("url") or "")
                opened_url = await asyncio.to_thread(open_browser_url, url)
                response = {"ok": True, "opened_url": opened_url}
                logger.info("🔌 Tool open_browser(%r) -> %s", url, opened_url)
            elif name == SET_VISION_FUNCTION_NAME:
                enabled = bool(args.get("enabled"))
                if enabled and not VISION_AVAILABLE:
                    response = {"ok": False, "enabled": False, "error": "Vision dependencies are not installed."}
                    logger.warning("🔌 Tool set_vision(%s) failed: VISION_AVAILABLE=False", enabled)
                else:
                    vision_enabled_runtime = enabled
                    status = "ON" if vision_enabled_runtime else "OFF"
                    response = {"ok": True, "enabled": vision_enabled_runtime, "status": status}
                    logger.info("🔌 Tool set_vision(%s) -> %s", enabled, status)
                    print(f"[Vision] Voice command → {status}")
            elif name == WEB_SEARCH_FUNCTION_NAME:
                query = str(args.get("query") or "")
                summary = await asyncio.to_thread(web_search_summary, query)
                response = {"ok": True, "results": summary}
                logger.info("🔎 Tool web_search(%r) -> %d chars", query, len(summary))
            elif name == MARKET_BRIEF_FUNCTION_NAME:
                summary = await asyncio.to_thread(get_market_summary)
                response = {"ok": True, "summary": summary}
                logger.info("📈 Tool get_market_brief -> %s", summary)
            elif name == PC_CONTROL_FUNCTION_NAME:
                action = str(args.get("action") or "")
                target = str(args.get("target") or "")
                response = await asyncio.to_thread(pc_control, action, target)
                logger.info("🖱️ Tool pc_control(%r, %r) -> ok=%s", action, target, response.get("ok"))
            elif name == REMEMBER_NOTE_FUNCTION_NAME:
                note = str(args.get("note") or "")
                category = str(args.get("category") or "general")
                response = await asyncio.to_thread(aurora_memory_store.remember_note, note, category)
                logger.info("🧠 Tool remember_note(category=%r) -> ok=%s", category, response.get("ok"))
            elif name == RECALL_MEMORY_FUNCTION_NAME:
                query = str(args.get("query") or "")
                response = await asyncio.to_thread(aurora_memory_store.recall_memory, query)
                logger.info("🧠 Tool recall_memory(%r) -> %s match(es)", query, len(response.get("matches", [])))
            else:
                response = {"ok": False, "error": f"Unknown tool: {name}"}
                logger.warning("🔌 Unknown tool call: %s args=%s", name, args)
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
            logger.exception("🔌 Tool %s failed", name)

        responses.append(types.FunctionResponse(id=call.id, name=name, response=response))

    if responses:
        await session.send_tool_response(function_responses=responses)
        mark_activity("bridge")


# ==============================================================================
# GEMINI LIVE CONFIG / SESSION RESUMPTION
# ==============================================================================
def build_live_config():
    kwargs = {
        "response_modalities": [types.Modality.AUDIO],
        "system_instruction": types.Content(parts=[types.Part.from_text(text=current_system_prompt())]),
        "speech_config": types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE_NAME)
            )
        ),
        "tools": build_live_tools(),
    }

    try:
        # Transcribe both sides so conversations auto-save to daily memory.
        kwargs["input_audio_transcription"] = types.AudioTranscriptionConfig()
        kwargs["output_audio_transcription"] = types.AudioTranscriptionConfig()
    except AttributeError:
        logger.warning("Gemini SDK lacks AudioTranscriptionConfig; conversation auto-capture disabled")

    if ENABLE_GEMINI_CONTEXT_COMPRESSION:
        try:
            kwargs["context_w