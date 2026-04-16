$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$InnoCompiler = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"

& (Join-Path $ProjectRoot "build-windows.ps1")

if (-not (Test-Path $InnoCompiler)) {
    Write-Host ""
    Write-Host "Inno Setup 6 was not found. Install it to create the installer:"
    Write-Host "https://jrsoftware.org/isdl.php"
    Write-Host ""
    Write-Host "Folder build is ready at:"
    Write-Host (Join-Path $ProjectRoot "dist\AudioTranscriber\AudioTranscriber.exe")
    exit 0
}

Write-Host "Creating Windows installer..."
& $InnoCompiler (Join-Path $ProjectRoot "installer-windows.iss")

Write-Host ""
Write-Host "Installer complete:"
Write-Host (Join-Path $ProjectRoot "installer\AudioTranscriberSetup.exe")
