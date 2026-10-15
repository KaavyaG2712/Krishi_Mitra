@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Stop-KrishiMitra.ps1" %*
set "KRISHIMITRA_EXIT_CODE=%ERRORLEVEL%"
if not "%KRISHIMITRA_EXIT_CODE%"=="0" (
  echo.
  echo KrishiMitra could not stop cleanly. Check the message above.
  pause
)
endlocal & exit /b %KRISHIMITRA_EXIT_CODE%
