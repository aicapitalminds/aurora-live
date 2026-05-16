# Aurora Smoke Tests

Run these before the weekly GitHub save.

## 1. Static secret check

From WSL or Git Bash:

```bash
git status --short
git diff --cached
```

Confirm that these are not staged:

- `.env`
- real `start-aurora.bat`
- logs
- API keys
- OAuth tokens

## 2. Python syntax check

From Windows inside `C:\aurora-live`:

```bat
.\.venv\Scripts\python.exe -m py_compile aurora-live.py check_audio.py
```

## 3. Audio device check

```bat
.\.venv\Scripts\python.exe check_audio.py
```

Expected: VoiceMeeter output is detected.

## 4. Launch smoke test

```bat
start-aurora.bat
```

Expected:

- microphone device resolved
- speaker device resolved
- Gemini Live session starts
- Live2D websocket starts on port 8770
- no immediate crash loop

## 5. OBS/Live2D visual check

Expected:

- Aurora model appears in OBS/browser source
- status indicator becomes OK
- mouth moves when Aurora speaks

## 6. Bridge check

Expected:

- Hermes/Twitch/Discord bridge events reach Aurora when the bridge is running
- if bridge is offline, Aurora voice still works and logs the bridge issue explicitly
