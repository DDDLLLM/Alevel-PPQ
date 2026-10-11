@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -3 -m venv .venv
if errorlevel 1 goto fail
fc /b requirements.txt .venv\requirements.installed >nul 2>&1
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto fail
  copy /y requirements.txt .venv\requirements.installed >nul
)
.venv\Scripts\python.exe app.py
pause
exit /b
:fail
echo Setup failed. Install Python 3.10+ and check network access to PyPI.
pause
exit /b 1
