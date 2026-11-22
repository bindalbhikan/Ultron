@echo off
REM Runs one bot once on this PC with the project .env:  scripts\local\run_local.bat ajio-tat --xlsx
cd /d "%~dp0..\.."
if not exist output mkdir output
REM the uv venv (scripts\local\setup_pc.ps1), else the system Python
set PY=python
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
%PY% run.py %* >> output\local_run.log 2>&1
