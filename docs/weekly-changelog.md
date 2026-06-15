# Weekly Changelog

Use this file for human-readable weekly notes before/after each GitHub save.

## 2026-06-15

### Weekly backup summary

- Updated `aurora-live.py` with the latest runtime and interaction changes.
- Added browser viewer prototypes: `aurora-codex-viewer.html`, `aurora-rodin-viewer.html`, and `rodin-models/rodin-preview.html`.
- Added new avatar/model asset folders for Live2D packaging and Rodin exports: `codex-avatar-assets/` and `rodin-models/`.
- Added `start-rodin-viewer-server.bat` for local viewer serving and `video-inspect/` reference frames for inspection.

## 2026-05-16

### Repository safety setup

- Added private repo README.
- Added `.gitignore` for API keys, `.env`, logs, virtual environments, and real local launchers.
- Added safe `start-aurora.example.bat` template.
- Added architecture, runbook, and smoke-test docs.
- Identified that the current real `start-aurora.bat` contains a Google API key and must stay untracked/private.

### Current system summary

- Windows gaming PC runs `aurora-live.py` for Gemini Live voice, audio routing, screen/vision, and Live2D lip-sync.
- OBS renders `aurora-viewer.html` as the Live2D source.
- Linux/spokserver bridge is planned/used for Twitch/Discord intelligence and future viewer memory/interaction queue.

### Next public update idea

Create a sanitized public showcase repo explaining the architecture and build path without exposing private tokens, local launchers, exact network details, or production-only files.
