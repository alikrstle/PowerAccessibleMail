@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_power_accessible_mail.ps1"
set "APP_EXIT_CODE=%ERRORLEVEL%"
pause
exit /b %APP_EXIT_CODE%
