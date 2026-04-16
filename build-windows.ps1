$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$DistExe = Join-Path $ProjectRoot "dist\AudioTranscriber\AudioTranscriber.exe"
$env:AUDIOTRANSCRIBER_PROFILE = "prod"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

$RunningApp = Get-Process AudioTranscriber -ErrorAction SilentlyContinue
if ($RunningApp) {
    Write-Host "AudioTranscriber is still running. Close it before building."
    Write-Host "Running process id(s): $($RunningApp.Id -join ', ')"
    Write-Host ""
    Write-Host "Close the app from its context menu, or run:"
    Write-Host "Stop-Process -Name AudioTranscriber"
    exit 1
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtual environment..."
    Invoke-Checked -Description "Virtual environment creation" -Command {
        python -m venv (Join-Path $ProjectRoot ".venv")
    }
}

Write-Host "Installing/updating build dependencies..."
Invoke-Checked -Description "Local package install" -Command {
    & $VenvPython -m pip install -e $ProjectRoot
}
Invoke-Checked -Description "PyInstaller install" -Command {
    & $VenvPython -m pip install pyinstaller
}

Write-Host "Building production app..."
Invoke-Checked -Description "PyInstaller build" -Command {
    & $VenvPython -m PyInstaller (Join-Path $ProjectRoot "audiotranscriber.spec") --noconfirm --clean
}

Write-Host ""
Write-Host "Build complete:"
Write-Host $DistExe
