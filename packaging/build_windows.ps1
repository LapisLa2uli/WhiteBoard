$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

python packaging/generate_icons.py
if ($LASTEXITCODE -ne 0) { throw "Failed to generate logo.ico / logo.icns" }

python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    python -m pip install --default-timeout=120 pyinstaller
}

Write-Host "Packaging WhiteBoard for Windows..."
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/whiteboard.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = Join-Path "dist" "WhiteBoard\WhiteBoard.exe"
if (-not (Test-Path $exe)) { throw "Build finished but $exe was not found" }

Write-Host "Windows build is at $exe"
Write-Host "On first launch the app asks before adding Desktop and Start menu shortcuts."
