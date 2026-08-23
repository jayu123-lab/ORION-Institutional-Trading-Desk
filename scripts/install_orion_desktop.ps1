$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "ORION Institutional Desk.lnk"
$StartScript = Join-Path $PSScriptRoot "start_orion.ps1"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""
$shortcut.WorkingDirectory = $Repo
$shortcut.Description = "ORION Institutional Trading Desk - paper mode"
$shortcut.IconLocation = "shell32.dll,13"
$shortcut.Save()
Write-Output "CREATED: $ShortcutPath"
