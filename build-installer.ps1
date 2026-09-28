param(
    [switch]$SkipAppBuild
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

if (-not $SkipAppBuild) {
    & python -m PyInstaller --noconfirm --clean --onefile --windowed --name ParallelChat `
        --add-data "templates;templates" --add-data "static;static" "$root\app.py"
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }
}

$compiler = @(
    "$root\tools\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $compiler) {
    throw 'Inno Setup 6 is required to make the installer. Install it from https://jrsoftware.org/isdl.php, then rerun this script.'
}

& $compiler "$root\ParallelChat.iss"
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
Write-Host "Installer created: $root\installer\ParallelChat-Setup.exe"
