# Aurora Architecture

## High-level flow

```text
Streamer mic / webcam / screen
        |
        v
aurora-live.py on Windows gaming PC
        |
        |-- microphone PCM -> Gemini Live API
        |-- optional screen frames -> Gemini Live API
        |-- model audio response -> Windows output device / VoiceMeeter
        |-- lip-sync values -> ws://localhost:8770
        |-- chat/context bridge -> ws://192.168.1.185:8765
        v
OBS scene
        |
        |-- desktop/game capture
        |-- browser source: aurora-viewer.html
        |-- VoiceMeeter routed audio
        v
Twitch stream
```

## Components

### Windows gaming PC

Runs the real-time audio/visual loop:

- `aurora-live.py`
- Gemini Live connection
- `sounddevice` microphone and speaker streams
- VoiceMeeter routing
- local lip-sync websocket on port `8770`
- OBS browser source rendering `aurora-viewer.html`

This must run on Windows native PowerShell/CMD because WSL cannot reliably access the same physical audio devices and virtual cables.

### spokserver / Linux server

Runs the wider automation layer:

- Hermes agent / `agenticaurorabot`
- Twitch/Discord bridge logic
- future chat filtering, viewer memory, and interaction queue

### Live2D viewer

`aurora-viewer.html` loads PixiJS + Cubism dependencies, opens a websocket to `localhost:8770`, and applies mouth-open values generated from Aurora's audio stream.

## Known local details

- Mic match string: `HD Pro Webcam`
- Speaker match string: `Voicemeeter AUX Input`
- Hermes bridge URL: `ws://192.168.1.185:8765`
- Live2D websocket port: `8770`

These values are private/local details. Do not copy them directly into the public repo except as generic examples.
