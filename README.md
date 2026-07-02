# Aurora Live

Aurora is a real-time AI streaming co-host: an Unreal Engine 5.8 MetaHuman that listens, talks (Gemini Live voice), lip-syncs, blinks, tracks the camera, and idles naturally — streamed to Twitch via OBS.

This repo contains the **Python voice agent + bridge** and all project docs, shared so you can copy it and build your own AI co-host. The Unreal project (maps, MetaHuman, C++ `AuroraRuntime` plugin) lives separately on the gaming PC (see [UE project](#ue-project-what-you-need-to-recreate)).

## Cost

Everything is free except one plugin:

- Unreal Engine 5.8, MetaHuman plugin, OBS — free
- All 3D assets (gaming room, wardrobe, props) — free from [Fab](https://fab.com)
- The character — stock MetaHuman **Zeva** preset, modified in the MetaHuman Character editor (skin, eyes, body, wardrobe); no paid character assets
- Gemini API — free tier works for testing; live use needs a paid key
- **[Runtime MetaHuman Lip Sync](https://georgy.dev) by Georgy Dev — the only paid component** (realistic NN lipsync; its blink/eyes-aim nodes are used too)

## Architecture

```
Mic ──> aurora-live.py (Gemini Live API, voice in/out)
              │
              ├─ speaker output (24 kHz PCM)
              ├─ websocket SERVER :8771 ── UE AuroraLiveController (client)
              │        avatar.audio.pcm (20 ms frames) -> Georgy lipsync
              │        avatar.state / gestures / text
              ├─ Hermes bridge (ws://<LAN>:8765, optional)
              └─ screen/vision loop (mss + Pillow)

UE 5.8 standalone (-game) ──> OBS Window/Game Capture ──> Twitch
```

## Requirements

**Machine** (single Windows gaming PC): Windows 11, decent GPU (built on 7800X3D / 32 GB / 24 GB GPU), physical audio devices (VoiceMeeter virtual cables supported). Runs on Windows, not WSL — `sounddevice` must see real devices.

**Software**
- Python 3.12+ (`pip install -r requirements.txt` in a venv)
- Unreal Engine 5.8 + MetaHuman plugin
- [Runtime MetaHuman Lip Sync](https://georgy.dev) plugin by Georgy Dev (realistic NN lipsync)
- OBS Studio
- A Google AI Studio API key (Gemini Live)
- Optional: Epic's official ModelContextProtocol UE plugin + `cloudflared` if you want an AI agent to edit the project live (see `Aurora_UE_MCP_Integration.md`)

## Setup

1. Clone into `C:\aurora-live` (paths in the launchers assume this).
2. `python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`
3. Copy `start-aurora.example.bat` → `start-aurora.bat`, set your `GOOGLE_API_KEY` and device names inside. **`start-aurora.bat` is gitignored — never commit it.**
4. Set up the UE side (see next section), then launch everything with `Launch_Aurora_Stream.bat` — it kills stale processes, starts the voice agent, waits for port 8771, then boots UE straight into the stage map as a standalone game. Do **not** also run `start-aurora.bat` manually (port 8771 collision).
5. Point OBS at the UE game window (Window/Game Capture).

## UE project (what you need to recreate)

The full Unreal project (maps, MetaHuman assets) isn't in this repo, but the custom C++ plugin is — everything else is rebuildable from stock parts:

1. UE 5.8 project with a MetaHuman character (stock Zeva preset, modify to taste) and the Georgy lipsync plugin installed.
2. Copy `unreal/Plugins/AuroraRuntime/` into your project's `Plugins/` folder and let UE compile it. It provides `AuroraLiveController` — an actor that connects as websocket client to `ws://127.0.0.1:8771`, feeds received PCM into the Georgy `RealisticLipSyncGenerator`, and exposes state/gesture events. **The controller actor must be placed in every level** or lipsync silently breaks.
3. Face AnimBP (`ABP_Aurora_Face` pattern): Copy Pose From Mesh → Control Rig (blink L/R from `UpdateMetaHumanAutoBlink`) → Runtime MetaHuman Eyes Aim (target = player camera location) → Blend Realistic MetaHuman Lip Sync → Output. Set it as the Face component's Anim Class on the character (Preview-graph edits alone won't show in game).
4. Body idle: Body component → Use Animation Asset → `AS_MH_Neutral_Stand_Idle_Loop`, looping.
5. A stage level containing the character, `AuroraLiveController`, lights, PostProcessVolume, PlayerStart.

Detailed plans/history: `Aurora_Roadmap.md`, `Aurora_FaceAnimBP_Idle_Plan.md`, `Aurora_UE_MCP_Integration.md`, `docs/`.

## Hard-won gotchas

- **Audio must be sent in ~20 ms PCM frames** (960 bytes @ 24 kHz mono). UE's standalone websocket silently drops large (~20 KB) messages while the editor accepts them — mouth freezes only in `-game`. Already handled in `aurora-live.py`.
- Custom AnimGraph C++ nodes need their editor module set to **`UncookedOnly`** (not `Editor`) in the `.uplugin`, or the node vanishes when running uncooked `-game`.
- In launch `.bat` files call the UE exe with a **titled** `start "Aurora" "...exe" args` (or directly) — `start "" ...` makes UE open the Project Browser instead of the project.
- Standalone traps the mouse by default; fix in `Config/DefaultInput.ini`: `bCaptureMouseOnLaunch=False`, `DefaultViewportMouseCaptureMode=NoCapture`, `DefaultViewportMouseLockMode=DoNotLock`. Escape hatch: `Shift+F1`.
- Any idle/expression curves must be applied **after** the Georgy lipsync node — it overwrites the face curve set.
- Uncooked standalone cold-start is ~90 s; a game window appearing in ~10 s is a stale instance.

## Repo map

| Path | Purpose |
|---|---|
| `aurora-live.py` | Main Gemini Live voice agent + bridge server |
| `aurora_unreal_bridge.py` | UE avatar websocket bridge (port 8771) |
| `aurora_gemini_session.py` / `aurora_memory.py` / `aurora_connectors.py` / `aurora_pc_control.py` | Session resume, memory, connectors, PC control |
| `unreal/Plugins/AuroraRuntime/` | UE C++ plugin: AuroraLiveController, bridge component, face idle anim node |
| `Launch_Aurora_Stream.bat` | One-click stream launcher (voice agent + UE standalone) |
| `start-aurora.example.bat` | Template for the secret-holding local launcher |
| `tests/`, `smoke_unreal_bridge_ws.py` | Unit + smoke tests |
| `docs/` | Runbook, smoke tests, changelog |

## Security rules

Never commit: API keys/tokens, `.env`, the real `start-aurora.bat`, logs, session-state JSON, `memory/` exports, or private credentials. `.gitignore` enforces this — check `git status` before every push.
