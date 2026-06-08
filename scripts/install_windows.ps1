param(
    [string]$SourceDir = "",
    [string]$InstallDir = "",
    [switch]$NoDesktopShortcut
)

$ErrorActionPreference = "Stop"

function Get-AppName {
    return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String("57q/5LiL6Imy5Y2h6YeH6ZuG5bel5YW36ZuG"))
}

$AppName = Get-AppName
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path -LiteralPath (Join-Path $ScriptRoot "..")

if ([string]::IsNullOrWhiteSpace($SourceDir)) {
    $SourceDir = Join-Path -Path $ProjectRoot.Path -ChildPath (Join-Path -Path "dist" -ChildPath $AppName)
}

if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = Join-Path $env:LOCALAPPDATA $AppName
}

$ResolvedSource = Resolve-Path -LiteralPath $SourceDir
$ExpectedExe = Join-Path $ResolvedSource.Path "$AppName.exe"

if (-not (Test-Path -LiteralPath $ExpectedExe)) {
    throw "Executable not found: $ExpectedExe. Build with PyInstaller first."
}

$InstallDirFull = [System.IO.Path]::GetFullPath($InstallDir)
$LocalAppDataFull = [System.IO.Path]::GetFullPath($env:LOCALAPPDATA)
if (-not $InstallDirFull.StartsWith($LocalAppDataFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Install directory must be under LOCALAPPDATA: $InstallDirFull"
}

if (Test-Path -LiteralPath $InstallDirFull) {
    Remove-Item -Recurse -Force -LiteralPath $InstallDirFull
}

New-Item -ItemType Directory -Force -Path $InstallDirFull | Out-Null
Get-ChildItem -Force -LiteralPath $ResolvedSource.Path | ForEach-Object {
    Copy-Item -Recurse -Force -LiteralPath $_.FullName -Destination $InstallDirFull
}

$InstalledExe = Join-Path $InstallDirFull "$AppName.exe"
if (-not (Test-Path -LiteralPath $InstalledExe)) {
    throw "Install failed, executable not found after copy: $InstalledExe"
}

if (-not $NoDesktopShortcut) {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $Desktop "$AppName.lnk"
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $InstalledExe
    $Shortcut.WorkingDirectory = $InstallDirFull
    $Shortcut.IconLocation = $InstalledExe
    $Shortcut.Description = $AppName
    $Shortcut.Save()
}

Write-Host "Installed: $InstalledExe"
if (-not $NoDesktopShortcut) {
    Write-Host "Desktop shortcut: $ShortcutPath"
}
