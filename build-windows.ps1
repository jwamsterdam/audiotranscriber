$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$env:AUDIOTRANSCRIBER_PROFILE = "prod"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtual environment..."
    python -m venv (Join-Path $ProjectRoot ".venv")
}

Write-Host "Installing/updating build dependencies..."
& $VenvPython -m pip install -e $ProjectRoot
& $VenvPython -m pip install pyinstaller

Write-Host "Building production app..."
& $VenvPython -m PyInstaller (Join-Path $ProjectRoot "audiotranscriber.spec") --noconfirm --clean

Write-Host ""
Write-Host "Build complete:"
Write-Host (Join-Path $ProjectRoot "dist\AudioTranscriber\AudioTranscriber.exe")
