$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Get-AppVersion {
    $value = python -c "from app.branding import APP_VERSION; print(APP_VERSION)"
    if ($LASTEXITCODE -ne 0 -or -not $value) {
        throw "Could not read APP_VERSION from app.branding"
    }
    return $value.Trim()
}

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

python packaging/generate_icons.py
if ($LASTEXITCODE -ne 0) { throw "Failed to generate logo.ico / logo.icns" }

python packaging/generate_version_info.py
if ($LASTEXITCODE -ne 0) { throw "Failed to generate Windows version info" }

python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    python -m pip install --default-timeout=120 pyinstaller
}

$version = Get-AppVersion
Write-Host "Packaging WhiteBoard $version for Windows..."
python -c "import flet, flet_desktop.version as v; print('flet', flet.version.flet_version, 'flet-desktop', v.version); raise SystemExit(0 if flet.version.flet_version == v.version else 1)"
if ($LASTEXITCODE -ne 0) { throw "flet and flet-desktop versions must match" }

python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/whiteboard.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = Join-Path "dist" "WhiteBoard\WhiteBoard.exe"
if (-not (Test-Path $exe)) { throw "Build finished but $exe was not found" }

$toc = Get-ChildItem -Path "build" -Recurse -Filter "Analysis-00.toc" | Select-Object -First 1
if (-not $toc -or -not (Select-String -Path $toc.FullName -Pattern "flet_desktop" -Quiet)) {
    throw "PyInstaller did not collect flet_desktop; the Windows app would fail to start"
}

$iscc = Get-Iscc
$rootIss = $Root.Replace("\", "/")
$iss = Join-Path $PSScriptRoot "whiteboard.iss"
Write-Host "Building installer with $iscc"
& $iscc "/DAppVersion=$version" "/DSourceRoot=$rootIss" $iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

$setup = Join-Path "dist" "WhiteBoard-Setup.exe"
if (-not (Test-Path $setup)) { throw "Installer was not created at $setup" }

Write-Host "Windows app is at $exe"
Write-Host "Installer is at $setup"
Write-Host "Installing or upgrading replaces the previous copy in %LOCALAPPDATA%\Programs\WhiteBoard."
Write-Host "Desktop and Start menu (Windows Search) shortcuts keep the same names and are retargeted automatically."
