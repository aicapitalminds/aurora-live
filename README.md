# Aurora Live - Private Project Repository

Aurora is Attila's AI streaming co-host for Twitch/Discord: a real-time voice + Live2D companion that can listen, speak, react visually, and connect to the wider stream automation stack.

This repository is the private source-of-truth backup for the live system.

## Current live components

- `aurora-live.py` - Gemini Live voice agent, microphone input, speaker output, screen/vision loop, Live2D lip-sync websocket, Hermes bridge.
- `aurora-viewer.html` - transparent Live2D browser source for OBS.
- `check_audio.py` - helper for checking Windows audio/VoiceMeeter devices.
- `live2d-models/` - local Live2D model assets used by the viewer.
- `start-aurora.example.bat` - safe template for the local Windows launcher.

## Security rules

Never commit:

- API keys or OAuth tokens
- `.env` files
- the real `start-aurora.bat`
- logs containing runtime/private output
- private Discord/Twitch/Gemini/Hermes credentials
- personal viewer data or memory exports

The real launcher currently belongs only on the gaming PC. Use `start-aurora.example.bat` as the committed template.

## Local run notes

Aurora runs on the Windows gaming PC, not WSL, because `sounddevice`/audio routing must see physical Windows devices and VoiceMeeter virtual cables.

Typical Windows launch:

```bat
cd /d C:\aurora-live
start-aurora.bat
```

OBS browser source should point at `aurora-viewer.html` or a locally served equivalent.

## Weekly maintenance ritual

1. Run a smoke test.
2. Review changes with `git status` and `git diff`.
3. Confirm no secrets are staged.
4. Commit private repo changes.
5. Push to GitHub.
6. Update the public showcase repo only with sanitized lessons, diagrams, and safe examples.

See `docs/smoke-tests.md`, `docs/runbook.md`, and `docs/weekly-changelog.md`.
