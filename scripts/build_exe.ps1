$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"

$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name button-clicker `
    --collect-all playwright `
    --paths src `
    --distpath dist `
    --workpath build `
    "scripts\entry.py" 2>&1 | Out-Host
$buildExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousPreference

if ($buildExitCode -ne 0) {
    throw "PyInstaller failed with exit code $buildExitCode"
}

$localConfig = Join-Path $root "config.local.json"
if (Test-Path $localConfig) {
    Copy-Item $localConfig (Join-Path $root "dist\config.local.json") -Force
    Write-Output "copied config.local.json into dist"
}

Write-Output "built: $(Join-Path $root 'dist\button-clicker.exe')"
