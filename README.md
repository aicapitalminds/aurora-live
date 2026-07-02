# Aurora Live

Aurora is a real-time AI streaming co-host: an Unreal Engine 5.8 MetaHuman that listens, talks (Gemini Live voice), lip-syncs, blinks, tracks the camera, and idles naturally — streamed to Twitch via OBS.

This repo contains the **Python voice agent + bridge** and all project docs. The Unreal project (maps, MetaHuman, C++ `AuroraRuntime` plugin) lives separately on the gaming PC (see [UE project](#ue-project-what-you-need-to-recreate)).

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
2. `python -m venv .venv && .venv\Scripts\pip i