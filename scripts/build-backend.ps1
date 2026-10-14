$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$pythonExe = $env:SEKY_BUILD_PYTHON
if (-not $pythonExe) {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        & py -3 -c "import sys; print(sys.executable)" | ForEach-Object { $pythonExe = $_.Trim() }
    }
}
if (-not $pythonExe) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) { $pythonExe = $pythonCommand.Source }
}
if (-not $pythonExe -or -not (Test-Path -LiteralPath $pythonExe)) {
    throw "A Python 3.10+ installation is needed only to build the installer. Install Python from python.org, then run pnpm run dist:win again. The finished Seky Barcode app does not require Python."
}

& $pythonExe -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 'Python 3.10 or newer is required.')"
if ($LASTEXITCODE -ne 0) { throw "Python 3.10 or newer is required to build the backend." }
& $pythonExe -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    & $pythonExe -m pip install "PyInstaller==6.22.3"
    if ($LASTEXITCODE -ne 0) { throw "Could not install PyInstaller. Check your internet connection and try again." }
}

$buildRoot = Join-Path $root "backend_build"
$distDir = Join-Path $buildRoot "dist"
$workDir = Join-Path $buildRoot "work"
$specDir = Join-Path $buildRoot "spec"
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
$dataArgs = @(
    "--add-data", "$(Join-Path $root 'index.html');.",
    "--add-data", "$(Join-Path $root 'assets\vendor');assets/vendor"
)
& $pythonExe -m PyInstaller --noconfirm --clean --onefile --noconsole `
    --name SekyBarcodeBackend `
    --distpath $distDir --workpath $workDir --specpath $specDir `
    @dataArgs (Join-Path $root "app_server.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller could not build the local database service." }

$backendDir = Join-Path $root "backend"
New-Item -ItemType Directory -Force -Path $backendDir | Out-Null
Copy-Item -LiteralPath (Join-Path $distDir "SekyBarcodeBackend.exe") -Destination (Join-Path $backendDir "SekyBarcodeBackend.exe") -Force
Write-Host "Backend ready: $(Join-Path $backendDir 'SekyBarcodeBackend.exe')"
