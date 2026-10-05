param(
    [string]$Python = "python",
    [switch]$Release,
    [switch]$SkipInstaller
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE)" }
}

function Get-Iscc {
    $candidates = @(
        $env:ISCC,
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        (Join-Path $PSScriptRoot "tools\InnoSetup\ISCC.exe"),
        (Join-Path $Root "archive\original\packaging\tools\InnoSetup\ISCC.exe")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
    throw "Install Inno Setup 6.7.3, or set ISCC to its compiler path."
}

$thumbprint = $env:WINDOWS_SIGN_THUMBPRINT
$signTool = $env:SIGNTOOL
if (-not $signTool) {
    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) { $signTool = $command.Source }
}
if ($thumbprint -and $thumbprint -notmatch '^[A-Fa-f0-9]{40}$') { throw "Invalid certificate thumbprint" }
if ($thumbprint -and -not $signTool) { throw "Set SIGNTOOL to the Windows SDK signtool.exe" }
if ($Release -and (-not $thumbprint -or $SkipInstaller)) {
    throw "Release requires WINDOWS_SIGN_THUMBPRINT and a signed installer"
}

Invoke-Checked $Python @("packaging/check_environment.py", "windows")
$prepare = @("packaging/prepare.py", "windows")
if ($Release) { $prepare += "--release" }
Invoke-Checked $Python $prepare
$version = (& $Python -c "from version import APP_VERSION; print(APP_VERSION)").Trim()
$env:WHITEBOARD_BUILD_INFO = Join-Path $Root "build\windows\build-info.json"
$env:PYINSTALLER_CONFIG_DIR = Join-Path $Root "build\pyinstaller-cache"
Invoke-Checked $Python @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", "dist", "--workpath", "build/windows", "packaging/whiteboard.spec")
$exe = Join-Path $Root "dist\WhiteBoard\WhiteBoard.exe"
foreach ($resource in @("index.html", "app.js", "app.css", "tabs.html", "tabs.js")) {
    if (-not (Test-Path (Join-Path $Root "dist\WhiteBoard\_internal\static\$resource"))) { throw "Missing packaged $resource" }
}
if ($thumbprint) {
    Invoke-Checked $signTool @("sign", "/sha1", $thumbprint, "/fd", "SHA256", "/tr", "http://timestamp.digicert.com", "/td", "SHA256", $exe)
    Invoke-Checked $signTool @("verify", "/pa", $exe)
} else { Write-Warning "Development build is unsigned; use -Release for distributable builds." }

$savedDataDir = $env:WHITEBOARD_DATA_DIR
try {
    $env:WHITEBOARD_DATA_DIR = Join-Path $Root ("build\smoke-" + [guid]::NewGuid().ToString("N"))
    $process = Start-Process -FilePath $exe -ArgumentList "--selftest" -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(120000)) { Stop-Process -Id $process.Id; throw "Packaged smoke test timed out" }
    if ($process.ExitCode -ne 0) { throw "Packaged smoke test failed: $($process.ExitCode)" }
} finally { $env:WHITEBOARD_DATA_DIR = $savedDataDir }

$artifacts = @($exe)
if (-not $SkipInstaller) {
    $iscc = Get-Iscc
    $arguments = @("/DAppVersion=$version", "/DSourceRoot=$Root")
    if ($thumbprint) {
        $arguments += "/DSignRelease=1"
        $arguments += ('/SWhiteBoard="{0}" sign /sha1 {1} /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $f' -f $signTool, $thumbprint)
    }
    $arguments += (Join-Path $PSScriptRoot "whiteboard.iss")
    Invoke-Checked $iscc $arguments
    $setup = Join-Path $Root "dist\WhiteBoard-$version-Setup.exe"
    if (-not (Test-Path $setup)) { throw "Installer was not created" }
    if ($thumbprint) { Invoke-Checked $signTool @("verify", "/pa", $setup) }
    $artifacts += $setup
}
$artifacts | ForEach-Object {
    $hash = Get-FileHash -LiteralPath $_ -Algorithm SHA256
    $relative = $_.Substring((Join-Path $Root 'dist').Length + 1).Replace('\', '/')
    "$($hash.Hash.ToLowerInvariant())  $relative"
} | Set-Content -Encoding ascii (Join-Path $Root "dist\SHA256SUMS-windows.txt")
Copy-Item -LiteralPath $env:WHITEBOARD_BUILD_INFO -Destination (Join-Path $Root "dist\build-info-windows.json")
Write-Host "Build and packaged smoke test passed. Artifacts: $($artifacts -join ', ')"
