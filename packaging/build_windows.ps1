param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$buildRoot = Join-Path $repoRoot "build\windows"
$venvPython = Join-Path $buildRoot "venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $Python -m venv (Join-Path $buildRoot "venv")
    if ($LASTEXITCODE -ne 0) { throw "Unable to create build environment" }
}

& $venvPython -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    & $venvPython -m pip install "pyinstaller==6.22.3"
    if ($LASTEXITCODE -ne 0) { throw "Unable to install PyInstaller" }
}

$src = Join-Path $repoRoot "src"
$assets = Join-Path $src "fanqie_short_story\web"
$entry = Join-Path $PSScriptRoot "launcher.py"
$dist = Join-Path $repoRoot "dist"
$work = Join-Path $buildRoot "work"
$spec = Join-Path $buildRoot "spec"

& $venvPython -m PyInstaller `
    --noconfirm `
    --onefile `
    --windowed `
    --name "FanqieShortStoryExporter" `
    --paths $src `
    --add-data "$assets;fanqie_short_story/web" `
    --distpath $dist `
    --workpath $work `
    --specpath $spec `
    $entry
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$exe = Join-Path $dist "FanqieShortStoryExporter.exe"
$license = Join-Path $dist "LICENSE"
$readme = Join-Path $dist "README.md"
Copy-Item -LiteralPath (Join-Path $repoRoot "LICENSE") -Destination $license -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README.md") -Destination $readme -Force
$versionMatch = Select-String -LiteralPath (Join-Path $repoRoot "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $versionMatch) { throw "Unable to read package version" }
$version = $versionMatch.Matches.Groups[1].Value
$archive = Join-Path $dist "FanqieShortStoryExporter-$version-Windows.zip"
Compress-Archive -LiteralPath @($exe, $license, $readme) -DestinationPath $archive -Force

Write-Output $exe
Write-Output $archive
