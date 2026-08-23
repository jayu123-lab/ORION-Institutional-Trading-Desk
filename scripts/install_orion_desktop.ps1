$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot

function Resolve-OrionDesktop {
  # Shell Namespace 0x10 and SHGetKnownFolderPath both follow OneDrive/Known Folder redirection.
  $shell = New-Object -ComObject Shell.Application
  $shellDesktop = $shell.Namespace(0x10)
  if ($shellDesktop -and $shellDesktop.Self.Path -and (Test-Path -LiteralPath $shellDesktop.Self.Path)) {
    return $shellDesktop.Self.Path
  }

  if (-not ("OrionKnownFolders" -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class OrionKnownFolders {
  [DllImport("shell32.dll")]
  public static extern int SHGetKnownFolderPath(ref Guid folderId, uint flags, IntPtr token, out IntPtr path);
}
'@
  }
  $folderId = [Guid]'B4BFCC3A-DB2C-424C-B029-7FE99A87C641'
  $pathPtr = [IntPtr]::Zero
  $result = [OrionKnownFolders]::SHGetKnownFolderPath([ref]$folderId, 0, [IntPtr]::Zero, [ref]$pathPtr)
  if ($result -eq 0) {
    try {
      $knownPath = [Runtime.InteropServices.Marshal]::PtrToStringUni($pathPtr)
    } finally {
      [Runtime.InteropServices.Marshal]::FreeCoTaskMem($pathPtr)
    }
    if ($knownPath -and (Test-Path -LiteralPath $knownPath)) { return $knownPath }
  }

  $environmentPath = [Environment]::GetFolderPath("Desktop")
  if ($environmentPath -and (Test-Path -LiteralPath $environmentPath)) { return $environmentPath }
  $profilePath = Join-Path $env:USERPROFILE "Desktop"
  if (Test-Path -LiteralPath $profilePath) { return $profilePath }
  if ($env:OneDrive) {
    $oneDrivePath = Join-Path $env:OneDrive "Desktop"
    if (Test-Path -LiteralPath $oneDrivePath) { return $oneDrivePath }
  }
  throw "Unable to resolve the Windows desktop folder."
}

$Desktop = Resolve-OrionDesktop
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
Write-Output "DESKTOP RESOLVED: $Desktop"
Write-Output "SHORTCUT CREATED: $ShortcutPath"
Write-Output "SHORTCUT EXISTS: $([bool](Test-Path -LiteralPath $ShortcutPath))"
Write-Output "SHORTCUT SIZE: $((Get-Item -LiteralPath $ShortcutPath).Length) bytes"
Write-Output "TARGET: $($shortcut.TargetPath)"
Write-Output "ARGUMENTS: $($shortcut.Arguments)"
