@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "VENV_PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"
set "AUDIOTRANSCRIBER_PROFILE=dev"

if not exist "%VENV_PYTHON%" (
    echo Creating virtual environment...
    python -m venv "%PROJECT_ROOT%.venv"
)

echo Installing/updating local package...
"%VENV_PYTHON%" -m pip install -e "%PROJECT_ROOT%"

echo Starting AudioTranscriber...
"%VENV_PYTHON%" -m audiotranscriber.main
