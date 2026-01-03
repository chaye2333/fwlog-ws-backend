@echo off
setlocal

set SCRIPT_DIR=%~dp0
set BOT_DIR=%SCRIPT_DIR%fwlog_ws_backend
set VENV_DIR=%BOT_DIR%\.venv
set REQ_FILE=%BOT_DIR%\requirements.txt

if not exist "%BOT_DIR%" (
  echo [ERROR] fwlog_ws_backend folder not found. Please put this bat in project root.
  pause
  exit /b 1
)

set PYTHON=python

if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo Creating virtual environment...
  "%PYTHON%" -m venv "%VENV_DIR%"
)

call "%VENV_DIR%\Scripts\activate.bat"
"%PYTHON%" -m pip install --upgrade pip
if exist "%REQ_FILE%" (
  echo Installing requirements...
  "%PYTHON%" -m pip install -r "%REQ_FILE%"
)

cd /d "%SCRIPT_DIR%"
echo Starting fwlog bot...
"%PYTHON%" fwlog_ws_backend/fwlog_ws_bot.py

echo.
echo fwlog bot exited. Press any key to close this window...
pause >nul

endlocal
