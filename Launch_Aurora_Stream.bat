@echo off
REM ============================================================
REM  Aurora one-click stream launcher
REM  - Kills any previous Aurora processes (prevents port 8771 /
REM    microphone / GPU collisions that jam lipsync + expressions)
REM  - Starts the Gemini voice agent (voice + lipsync + facial brain)
REM  - Boots Aurora into game mode on the stage
REM  - Closes this launcher window afterwards
REM  Do NOT run start-aurora.bat separately - this handles it.
REM ============================================================

REM --- 0) Clean slate: stop any old voice agent + Unreal ---
taskkill /F /T /FI "WINDOWTITLE eq Aurora Live*"          >nul 2>&1
taskkill /F /T /FI "WINDOWTITLE eq Aurora Voice Agent*"   >nul 2>&1
taskkill /F /IM UnrealEditor.exe                          >nul 2>&1

REM Give Windows a moment to release port 8771 and the audio devices.
timeout /t 3 /nobreak >nul

REM --- 1) Start the voice agent (minimized). It must stay running. ---
start "Aurora Voice Agent" /min "C:\aurora-live\start-aurora.bat"

REM --- 2) Let it bind the bridge on port 8771 before Unreal connects. ---
timeout /t 6 /nobreak >nul

REM --- 3) Launch Aurora as a standalone game, then close this window. ---
start "Aurora" "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe" "C:\Users\AI\Documents\Unreal Projects\AuroraMetaHuman 5.8\AuroraMetaHuman.uproject" /Game/L_AuroraStage -game -windowed -ResX=1600 -ResY=900

exit
