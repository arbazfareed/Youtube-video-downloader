$ErrorActionPreference = "Stop"
$appFolder = Split-Path -Parent $MyInvocation.MyCommand.Path
$requirements = Join-Path $appFolder "requirements.txt"
$venvPython = Join-Path $appFolder ".venv\Scripts\python.exe"
$guiPython = Join-Path $appFolder ".venv\Scripts\pythonw.exe"
$guiEntry = Join-Path $appFolder "launch.py"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Smart Downloader 13.lnk"

if (-not (Test-Path -LiteralPath $requirements)) {
    throw "The app requirements file was not found: $requirements"
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $pythonLauncher) {
        throw "Python 3 was not found. Install Python 3.10 or newer, including the Python launcher and Tcl/Tk."
    }
    & $pythonLauncher.Source -3 -m venv (Join-Path $appFolder ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the app's Python environment (exit code $LASTEXITCODE)."
    }
}

if (-not (Test-Path -LiteralPath $guiPython)) {
    throw "The GUI Python executable was not found: $guiPython"
}

$pythonVersion = & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or [version]$pythonVersion -lt [version]"3.10") {
    throw "Smart Downloader requires Python 3.10 or newer."
}

& $venvPython -m pip install --disable-pip-version-check --no-input -r $requirements
if ($LASTEXITCODE -ne 0) {
    throw "Could not install app dependencies (exit code $LASTEXITCODE)."
}

$requirementsHash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash.ToLowerInvariant()
$stampPath = Join-Path $appFolder ".venv\.requirements-sha256"
Set-Content -LiteralPath $stampPath -Value $requirementsHash -Encoding ascii -NoNewline

if (-not (Test-Path -LiteralPath $guiEntry)) {
    throw "The app entry point was not found: $guiEntry"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.Description = "Open Smart Downloader 13.0"
$shortcut.IconLocation = "$env:SystemRoot\System32\SHELL32.dll, 13"
$shortcut.TargetPath = $guiPython
$shortcut.Arguments = "`"$guiEntry`""
$shortcut.WorkingDirectory = $appFolder
$shortcut.Save()

Write-Host "Desktop shortcut created: $shortcutPath"
Write-Host "Target: $($shortcut.TargetPath)"
