@echo off
setlocal
title Aurora Live (auto-restart watchdog)
cd /d C:\aurora-live

REM Copy this file to start-aurora.bat and fill in your real key locally.
REM Never commit start-aurora.bat to GitHub.
set "GOOGLE_API_KEY=YOUR_GOOGLE_API_KEY_HERE"
set "WATCHDOG_LOG=watchdog.log"
set "RESTART_DELAY=5"

set /a RUN_COUNT=0

:loop
set /a RUN_COUNT+=1
echo.
echo ============================================================
echo  [%DATE% %TIME%] Starting Aurora  (run #%RUN_COUNT%)
echo ============================================================
echo [%DATE% %TIME%] start run #%RUN_COUNT% >> "%WATCHDOG_LOG%"
echo.

.\.venv\Scripts\python.exe aurora-live.py
set EXIT_CODE=%ERRORLEVEL%

echo.
echo ============================================================
echo  [%DATE% %TIME%] Aurora exited  (code %EXIT_CODE%, run #%RUN_COUNT%)
echo ============================================================
echo [%DATE% %TIME%] exit run #%RUN_COUNT% code=%EXIT_CODE% >> "%WATCHDOG_LOG%"
echo.
echo Restarting in %RESTART_DELAY% seconds... press Ctrl+C now to stop the watchdog.
timeout /t %RESTART_DELAY% >nul

goto loop
