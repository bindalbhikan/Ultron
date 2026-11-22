@echo off
REM Runs one bot once on this PC with the project .env:  scripts\local\run_local.bat ajio-tat --xlsx
cd /d "%~dp0..\.."
set OUT=%ULTRON_OUTPUT%
if "%OUT%"=="" set OUT=%LOCALAPPDATA%\Ultron\output
if not exist "%OUT%" mkdir "%OUT%"
REM the uv venv (scripts\local\setup_pc.ps1), else the system Python
set PY=python
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
%PY% run.py %* >> "%OUT%\local_run.log" 2>&1
