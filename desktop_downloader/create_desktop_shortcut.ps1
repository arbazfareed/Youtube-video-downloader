$ErrorActionPreference = "Stop"
$appFolder = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = Join-Path $appFolder "Run Smart Downloader.bat"
$guiPython = Join-Path $appFolder ".venv\Scripts\pythonw.exe"
$guiEntry = Join-Path $appFolder "launch.py"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Smart Downloader.lnk"

if (-not (Test-Path -LiteralPath $launcher)) {
    throw "The app launcher was not found: $launcher"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.Description = "Open Smart Downloader"
$shortcut.IconLocation = "$env:SystemRoot\System32\SHELL32.dll, 13"
if ((Test-Path -LiteralPath $guiPython) -and (Test-Path -LiteralPath $guiEntry)) {
    $shortcut.TargetPath = $guiPython
    $shortcut.Arguments = "`"$guiEntry`""
} else {
    $shortcut.TargetPath = $launcher
    $shortcut.Arguments = ""
}
$shortcut.WorkingDirectory = $appFolder
$shortcut.Save()

Write-Host "Desktop shortcut created: $shortcutPath"
Write-Host "Target: $($shortcut.TargetPath)"
