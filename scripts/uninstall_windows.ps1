param(
    [string]$InstallDir = ""
)

$ErrorActionPreference = "Stop"

function Get-AppName {
    return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String("57q/5LiL6Imy5Y2h6YeH6ZuG5bel5YW36ZuG"))
}

$AppName = Get-AppName

if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = Join-Path $env:LOCALAPPDATA $AppName
}

$InstallDirFull = [System.IO.Path]::GetFullPath($InstallDir)
$LocalAppDataFull = [System.IO.Path]::GetFullPath($env:LOCALAPPDATA)
if (-not $InstallDirFull.StartsWith($LocalAppDataFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Install directory must be under LOCALAPPDATA: $InstallDirFull"
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "$AppName.lnk"

if (Test-Path -LiteralPath $ShortcutPath) {
    Remove-Item -Force -LiteralPath $ShortcutPath
}

if (Test-Path -LiteralPath $InstallDirFull) {
    Remove-Item -Recurse -Force -LiteralPath $InstallDirFull
}

Write-Host "Uninstalled: $AppName"
