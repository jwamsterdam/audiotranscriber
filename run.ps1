$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$env:AUDIOTRANSCRIBER_PROFILE = "dev"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtual environment..."
    python -m venv (Join-Path $ProjectRoot ".venv")
}

Write-Host "Installing/updating local package..."
& $VenvPython -m pip install -e $ProjectRoot

Write-Host "Starting AudioTranscriber..."
& $VenvPython -m audiotranscriber.main
