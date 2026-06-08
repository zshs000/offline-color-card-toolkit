param(
    [string]$InstallDir = ""
)

$ErrorActionPreference = "Stop"

function Get-AppName {
    return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String("57q/5LiL6Imy5Y2h6YeH6ZuG5bel5YW36ZuG"))
}

function Assert-UnderDirectory {
    param(
        [string]$Path,
        [string]$Parent
    )

    $FullPath = [System.IO.Path]::GetFullPath($Path)
    $Separators = @([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    $ParentPath = [System.IO.Path]::GetFullPath($Parent).TrimEnd($Separators)
    $ParentPrefix = $ParentPath + [System.IO.Path]::DirectorySeparatorChar
    if (-not $FullPath.StartsWith($ParentPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path must stay under install directory: $FullPath"
    }
    return $FullPath
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
    $AppExe = Assert-UnderDirectory -Path (Join-Path $InstallDirFull "$AppName.exe") -Parent $InstallDirFull
    $InternalDir = Assert-UnderDirectory -Path (Join-Path $InstallDirFull "_internal") -Parent $InstallDirFull

    foreach ($Path in @($AppExe, $InternalDir)) {
        if (Test-Path -LiteralPath $Path) {
            Remove-Item -Recurse -Force -LiteralPath $Path
        }
    }

    if (-not (Get-ChildItem -Force -LiteralPath $InstallDirFull)) {
        Remove-Item -Force -LiteralPath $InstallDirFull
    }
}

Write-Host "Uninstalled: $AppName"
