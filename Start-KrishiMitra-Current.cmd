@echo off
setlocal

rem Starts the latest code in the folder containing this file.
rem It clears stale KrishiMitra processes on ports 5173 and 8000 first.
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-KrishiMitra-Current.ps1" %*
set "KRISHIMITRA_EXIT_CODE=%ERRORLEVEL%"

if not "%KRISHIMITRA_EXIT_CODE%"=="0" (
  echo.
  echo KrishiMitra did not start. Check the error above and .codex-finalizer\logs.
  pause
)

endlocal & exit /b %KRISHIMITRA_EXIT_CODE%
