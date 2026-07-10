# Installs Python deps and adds a Startup-folder shortcut for Squat Reminder.
$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$pyw = Join-Path $scriptDir "squat_reminder.pyw"

Write-Host "Installing Python dependencies (pywebview, pystray, pillow)..."
pip install pywebview pystray pillow

$pythonwCmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
if ($pythonwCmd) {
    $pythonw = $pythonwCmd.Source
} else {
    $pythonExe = (Get-Command python.exe).Source
    $pythonw = Join-Path (Split-Path $pythonExe) "pythonw.exe"
}

$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "SquatReminder.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "`"$pyw`""
$shortcut.WorkingDirectory = $scriptDir
$shortcut.WindowStyle = 7
$shortcut.Description = "Hourly squat reminder"
$shortcut.Save()

Write-Host ""
Write-Host "Startup shortcut created at: $shortcutPath"
Write-Host "The reminder will now launch automatically at login."
Write-Host ""
Write-Host "To start it right now without rebooting, run:"
Write-Host "    & `"$pythonw`" `"$pyw`""
Write-Host ""
Write-Host "To uninstall, delete: $shortcutPath"
