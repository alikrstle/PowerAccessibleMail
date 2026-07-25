@echo off
cd /d "%~dp0"
python -m venv .venv
call .venv\Scripts\python.exe -m pip install --upgrade pip
call .venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
pause
