@echo off
setlocal

rem Double-click this file in Windows Explorer, or run it from PowerShell.
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-KrishiMitra.ps1"
set "KRISHIMITRA_EXIT_CODE=%ERRORLEVEL%"

if not "%KRISHIMITRA_EXIT_CODE%"=="0" (
  echo.
  echo KrishiMitra did not start. Read the error above, then press any key to close this window.
  pause >nul
)

endlocal & exit /b %KRISHIMITRA_EXIT_CODE%
