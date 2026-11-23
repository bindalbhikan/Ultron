# Make any Windows PC ready to work on this project. Safe to run again; no admin needed.
#
#   powershell -ExecutionPolicy Bypass -File scripts\local\setup_pc.ps1           set up / repair this PC
#   powershell -ExecutionPolicy Bypass -File scripts\local\setup_pc.ps1 -Backup   also copy the private files to Drive
#
# Layout (owner, 22 Nov 2026): the project lives at D:\ULTRON (a normal Git checkout, off Google Drive,
# whose desktop.ini files broke Git refs). No PC is fixed, so nothing that matters lives only here:
#   - code history: GitHub (push before leaving a PC)
#   - private files (.env, service_account.json, myntra_session*.json): a copy on Drive in
#     AGENT-PRIVATE\ULTRON, copied back here when missing (-Backup refreshes the Drive copy)
#   - Claude Code's memory for this project: a junction to AGENT-MEMORY\AGENT-ULTRON-BINDAL on Drive
#   - the Python venv: .venv in the project, built by uv from uv.lock
# On a new PC: git clone https://github.com/bindalbhikan/Ultron.git D:\ULTRON, then run this script.

param([switch]$Backup)
$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot)
$drive = "G:\My Drive\BINDAL EXPORTS\AGENT"
if (-not (Test-Path $drive)) { Write-Error "Google Drive for desktop is not at $drive; start it first." }

function Set-Junction([string]$link, [string]$target) {
    $item = Get-Item $link -Force -ErrorAction SilentlyContinue
    if ($item -and $item.LinkType -eq "Junction") {
        if ("$($item.Target)" -eq $target) { Write-Output "ok: $link -> $target"; return }
        $item.Delete()  # a junction to somewhere else: remove the link only, never its target
    } elseif ($item) {
        # notes written on this PC before the junction: keep them on Drive (Drive's copy wins a clash)
        Get-ChildItem $link -File | Where-Object { $_.Name -ne "desktop.ini" } | ForEach-Object {
            $dest = Join-Path $target $_.Name
            if (-not (Test-Path $dest)) { Copy-Item $_.FullName $dest }
        }
        Rename-Item $link "$(Split-Path $link -Leaf).local-backup-$(Get-Date -Format yyyyMMddHHmmss)"
    }
    New-Item -ItemType Directory -Force (Split-Path $link) | Out-Null
    New-Item -ItemType Junction -Path $link -Target $target | Out-Null
    Write-Output "linked: $link -> $target"
}

# 1. Git: a normal checkout
if (-not (Test-Path (Join-Path $root ".git\HEAD"))) { Write-Error "$root is not a Git checkout; clone it (see the top of this file)." }

# 2. Private files: from Drive when missing here; -Backup copies this PC's to Drive
$private = Join-Path $drive "AGENT-PRIVATE\ULTRON"
New-Item -ItemType Directory -Force $private | Out-Null
$names = @(".env", "service_account.json") + (Get-ChildItem $root -Filter "myntra_session*.json" -Name) +
         (Get-ChildItem $private -Filter "myntra_session*.json" -Name) | Sort-Object -Unique
foreach ($name in $names) {
    $here = Join-Path $root $name; $there = Join-Path $private $name
    if (-not (Test-Path $here) -and (Test-Path $there)) { Copy-Item $there $here; Write-Output "restored from Drive: $name" }
    if ($Backup -and (Test-Path $here)) { Copy-Item $here $there -Force; Write-Output "backed up to Drive: $name" }
    if (-not (Test-Path $here)) { Write-Output "missing: $name (not here and not on Drive)" }
}

# 3. Claude Code memory on Drive (the folder name is the project path with : \ / and spaces as -)
$memDrive = Join-Path $drive "AGENT-MEMORY\AGENT-ULTRON-BINDAL"
New-Item -ItemType Directory -Force $memDrive | Out-Null
$key = ($root -replace '[:\\/ ]', '-')
Set-Junction (Join-Path $env:USERPROFILE ".claude\projects\$key\memory") $memDrive

# 4. Python venv by uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Output "installing uv"
    powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
Remove-Item Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue  # the venv is the project's .venv
Push-Location $root
try {
    # uv's own Python, never the Microsoft Store one: the Store Python quietly writes %LOCALAPPDATA% into its
    # package folder, so the bots' output (%LOCALAPPDATA%\Ultron\output) landed out of sight (23 Nov 2026)
    $cfg = Join-Path $root ".venv\pyvenv.cfg"
    if ((Test-Path $cfg) -and (Select-String -Path $cfg -Pattern "WindowsApps|cpython-3.1[3-9]" -Quiet)) {
        Write-Output "venv not on uv's own Python 3.12: rebuilt"
        Remove-Item -Recurse -Force (Join-Path $root ".venv")
    }
    uv sync --all-extras --frozen --quiet --managed-python --python 3.12   # the version GitHub runs (setup action)
    uv pip install --quiet pytest ruff "pyright==1.1.414"
} finally { Pop-Location }
Write-Output "venv: $root\.venv (run bots with .venv\Scripts\python run.py <bot>; not plain 'uv run', which drops the extras)"

git -C $root status --short --branch | Select-Object -First 1
