# Copyright (c) 2026 Ubion ax center
#
# Prepare the bundled "payload" that ships inside the Tauri installer:
#
#   src-tauri/python/   ← python-build-standalone interpreter + site-packages
#   src-tauri/engine/   ← snapshot of the engine/ Python package
#
# Idempotent: running it twice is safe. Re-running with -Clean wipes the
# python tree and starts over (use after a requirements.txt change or a
# version bump).
#
# Why this script exists:
#   The two payload trees are .gitignored (114 MB / thousands of files),
#   so a fresh clone has no way to run the Tauri shell. `tauri build`
#   ALSO needs them to be present at the same paths. One script that
#   both dev and CI invoke keeps the inputs to `cargo tauri build`
#   reproducible.
#
# Inputs the script consumes:
#   $PSScriptRoot/.. = src-tauri/
#   $PSScriptRoot/../requirements.txt
#   $PSScriptRoot/../../engine/             ← source of truth, copied as-is
#
# Outputs:
#   $PSScriptRoot/../python/
#   $PSScriptRoot/../engine/

[CmdletBinding()]
param(
    # Wipe the python/ tree and re-download. Use when bumping the version
    # constant below or when the dependency tree gets cluttered.
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'

# ──────────────────────────────────────────────────────────────────────
# Version pins. Update both when bumping.
# ──────────────────────────────────────────────────────────────────────

# python-build-standalone tag (https://github.com/astral-sh/python-build-standalone/releases)
$PbsTag        = '20260510'
$PbsPython     = '3.13.13'
$PbsVariant    = 'x86_64-pc-windows-msvc-install_only_stripped'
$PbsAsset      = "cpython-$PbsPython+$PbsTag-$PbsVariant.tar.gz"
$PbsUrl        = "https://github.com/astral-sh/python-build-standalone/releases/download/$PbsTag/$PbsAsset"

# ──────────────────────────────────────────────────────────────────────

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$TauriRoot  = Resolve-Path (Join-Path $ScriptRoot '..')
$RepoRoot   = Resolve-Path (Join-Path $TauriRoot '..')

$PythonDir       = Join-Path $TauriRoot 'python'
$PythonExe       = Join-Path $PythonDir 'python.exe'
$SitePackages    = Join-Path $PythonDir 'Lib/site-packages'
$EngineSrc       = Join-Path $RepoRoot 'engine'
$EngineDst       = Join-Path $TauriRoot 'engine'
$Requirements    = Join-Path $TauriRoot 'requirements.txt'
$DownloadCache   = Join-Path $TauriRoot '.payload-cache'

function Write-Step($msg) {
    Write-Host "==> $msg" -ForegroundColor Cyan
}

# ──────────────────────────────────────────────────────────────────────
# Step 1 — embedded python interpreter
# ──────────────────────────────────────────────────────────────────────

if ($Clean -and (Test-Path $PythonDir)) {
    Write-Step "Removing existing python/ tree (--Clean)"
    Remove-Item -Recurse -Force $PythonDir
}

if (-not (Test-Path $PythonExe)) {
    Write-Step "Downloading python-build-standalone $PbsTag ($PbsVariant)"
    New-Item -ItemType Directory -Force -Path $DownloadCache | Out-Null
    $cachedTarball = Join-Path $DownloadCache $PbsAsset
    if (-not (Test-Path $cachedTarball)) {
        # `Invoke-WebRequest` with a progress hide for speed on slow shells.
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $PbsUrl -OutFile $cachedTarball
    }
    Write-Step "Extracting into src-tauri/python/"
    tar -xzf $cachedTarball -C $TauriRoot
    if (-not (Test-Path $PythonExe)) {
        throw "Extraction failed — python.exe not found at $PythonExe"
    }
} else {
    Write-Step "Embedded python already present, skipping download"
}

# ──────────────────────────────────────────────────────────────────────
# Step 2 — install runtime dependencies into site-packages
# ──────────────────────────────────────────────────────────────────────
#
# `--isolated` blocks the user's ~/AppData/Roaming/Python site-packages
# from short-circuiting "Requirement already satisfied"; `--target`
# forces installation into our embedded tree even though python.exe
# itself is the same interpreter.

if (-not (Test-Path $Requirements)) {
    throw "Missing requirements file: $Requirements"
}

Write-Step "Installing runtime dependencies into embedded site-packages"
# pip writes informational messages to stderr (cache hits, install
# progress). In Windows PowerShell 5.1 each such line is wrapped as a
# NativeCommandError and sets $? to false even when pip exits 0 — so
# we capture exit code explicitly and ignore the synthetic error stream.
& $PythonExe -m pip install --quiet --upgrade pip 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "pip self-upgrade failed (exit $LASTEXITCODE)" }
# `--upgrade` lets pip overwrite an existing target directory without
# bailing out — necessary because pip refuses by default when the
# requested package already lives in the target.
& $PythonExe -m pip install --isolated --no-user --upgrade --target $SitePackages -r $Requirements 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }

# ──────────────────────────────────────────────────────────────────────
# Step 3 — snapshot the engine/ Python package
# ──────────────────────────────────────────────────────────────────────
#
# We copy rather than symlink so the bundler sees a real directory tree
# at build time. __pycache__ is excluded because (a) Python regenerates
# it on first run and (b) absolute paths inside .pyc bytecode leak
# build-machine identity.

if (-not (Test-Path $EngineSrc)) {
    throw "Engine source not found at $EngineSrc"
}

Write-Step "Snapshotting engine/ into src-tauri/engine/"
if (Test-Path $EngineDst) {
    Remove-Item -Recurse -Force $EngineDst
}
robocopy $EngineSrc $EngineDst /MIR /XD __pycache__ .pytest_cache /NFL /NDL /NJH /NJS /NP | Out-Null
# robocopy uses exit codes 0-7 for success. Anything >= 8 is failure.
if ($LASTEXITCODE -ge 8) {
    throw "robocopy failed with exit $LASTEXITCODE"
}

# ──────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────

function Get-DirSize($path) {
    if (-not (Test-Path $path)) { return 0 }
    (Get-ChildItem -Recurse -File -ErrorAction SilentlyContinue $path |
        Measure-Object -Property Length -Sum).Sum
}

$pythonBytes = Get-DirSize $PythonDir
$engineBytes = Get-DirSize $EngineDst
$totalBytes  = $pythonBytes + $engineBytes

function Format-MB($bytes) { '{0:N1} MB' -f ($bytes / 1MB) }

Write-Host ''
Write-Host "Payload prepared:" -ForegroundColor Green
Write-Host ("  python/ = {0}" -f (Format-MB $pythonBytes))
Write-Host ("  engine/ = {0}" -f (Format-MB $engineBytes))
Write-Host ("  total   = {0}  (uncompressed; bundler applies LZMA)" -f (Format-MB $totalBytes))

# Explicit successful exit. Without this, a non-zero $LASTEXITCODE from
# the last native command (robocopy returns 1-7 on "success with files
# copied") would leak out and confuse callers like cargo's build.rs.
exit 0
