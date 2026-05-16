# Aurora Runbook

## Start Aurora

On the Windows gaming PC:

```bat
cd /d C:\aurora-live
start-aurora.bat
```

The real `start-aurora.bat` is intentionally ignored by git because it can contain the local Google API key. Keep `start-aurora.example.bat` updated as the safe template.

## Check audio devices

```bat
cd /d C:\aurora-live
.\.venv\Scripts\python.exe check_audio.py
```

If audio routing breaks after Windows/driver updates, update the device-name substrings inside `aurora-live.py` instead of hardcoding fragile device indices.

## OBS setup

- Add Aurora as a browser source.
- Use transparent background.
- Point it to `aurora-viewer.html` or a local server URL.
- Route Aurora audio through VoiceMeeter into the stream mix.

## Common failures

### Missing Google API key

Symptom: Gemini Live connection fails immediately.

Fix: confirm `GOOGLE_API_KEY` is set in the local launcher or shell.

### Audio device not found

Symptom: startup raises `No input/output audio device matching ... found`.

Fix: run `check_audio.py`, copy the exact working device-name substring into `aurora-live.py`, then restart.

### Live2D mouth not moving

Check:

1. `aurora-live.py` started without errors.
2. `aurora-viewer.html` is open in OBS/browser.
3. Browser source can connect to `ws://localhost:8770`.
4. Aurora is actually producing audio.

### Hermes bridge unavailable

Symptom: chat/context events do not arrive.

Fix: check the Linux server bridge process and local network connectivity. Aurora voice should still work if the bridge is down, but stream chat intelligence may be degraded.
