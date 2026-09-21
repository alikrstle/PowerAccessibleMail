@echo off
cd /d "%~dp0"
python -m venv --upgrade .venv
call .venv\Scripts\python.exe -m pip install --upgrade pip
call .venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-release.lock
pause
