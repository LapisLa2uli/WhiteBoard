$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Get-Iscc {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        (Join-Path $PSScriptRoot "tools\InnoSetup\ISCC.exe")
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) {
            return $path
        }
    }

    $tools = Join-Path $PSScriptRoot "tools"
    New-Item -ItemType Directory -Force -Path $tools | Out-Null
    $setup = Join-Path $tools "innosetup-setup.exe"
    $url = "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe"
    Write-Host "Downloading Inno Setup compiler..."
    Invoke-WebRequest -Uri $url -OutFile $setup
    $dir = Join-Path $tools "InnoSetup"
    Write-Host "Installing Inno Setup to $dir"
    & $setup /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER /SP- /DIR="$dir"
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup installer failed"
    }
    $iscc = Join-Path $dir "ISCC.exe"
    $deadline = (Get-Date).AddSeconds(30)
    while (-not (Test-Path $iscc) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 1
    }
    if (-not (Test-Path $iscc)) {
        throw "ISCC.exe was not found after installing Inno Setup"
    }
    return $iscc
}

python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    python -m pip install --default-timeout=120 pyinstaller
}

$version = "0.4.0"
Write-Host "Packaging WhiteBoard $version for Windows..."
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/whiteboard.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = Join-Path "dist" "WhiteBoard\WhiteBoard.exe"
if (-not (Test-Path $exe)) { throw "Build finished but $exe was not found" }
$index = Join-Path "dist" "WhiteBoard\_internal\static\index.html"
if (-not (Test-Path $index)) { throw "Packaged app is missing static\index.html" }

$iscc = Get-Iscc
$rootIss = $Root.Replace("\", "/")
$iss = Join-Path $PSScriptRoot "whiteboard.iss"
Write-Host "Building installer with $iscc"
& $iscc "/DAppVersion=$version" "/DSourceRoot=$rootIss" $iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

$setup = Join-Path "dist" "WhiteBoard-$version-Setup.exe"
if (-not (Test-Path $setup)) { throw "Installer was not created at $setup" }

Write-Host "Windows app is at $exe"
Write-Host "Installer is at $setup"
