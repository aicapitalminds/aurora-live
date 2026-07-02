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

**Machine** (single Windows gaming PC): Windows 11, decent GPU (built on 7800X3D / 32 GB / 24 GB GPU), physical audio devices (VoiceMeeter virtual cables support