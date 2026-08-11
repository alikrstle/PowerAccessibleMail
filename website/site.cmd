@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0site.ps1" %*
exit /b %errorlevel%
