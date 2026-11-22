# Make any Windows PC ready to work on this project. Safe to run again; no admin needed.
#
#   powershell -ExecutionPolicy Bypass -File scripts\local\setup_pc.ps1
#
# Rule (owner, 22 Nov 2026): no PC is fixed. Everything that matters lives on Google Drive (the
# project files, .env, service_account.json, the coding agents' memory) or on GitHub (the code
# history: push before leaving a PC). A PC holds only what this script can rebuild:
#
# 1. Git metadata in %USERPROFILE%\.ultron\git\AGENT-ULTRON-BINDAL.git (kept off Drive: Drive puts
#    desktop.ini into Git refs). Missing -> rebuilt from GitHub; the working files are not touched.
#    The Drive-synced `.git` pointer names C:/ProgramData/Ultron/git/AGENT-ULTRON-BINDAL.git, a
#    junction made here to the metadata above.
# 2. Claude Code's memory for this project: a junction to AGENT-MEMORY on Drive, so every PC reads
#    and writes the same notes.
# 3. The Python venv in %USERPROFILE%\.ultron\venv (uv, from uv.lock).

$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot)
$repoUrl = "https://github.com/bindalbhikan/Ultron.git"

function Set-Junction([string]$link, [string]$target) {
    $item = Get-Item $link -Force -ErrorAction SilentlyContinue
    if ($item -and $item.LinkType -eq "Junction") {
        if ("$($item.Target)" -eq $target) { Write-Output "ok: $link -> $target"; return }
        $item.Delete()  # a junction to somewhere else: remove the link only, never its target
    } elseif ($item) {
        Write-Error "$link is a real folder, not a junction; look at it before removing it."
    }
    New-Item -ItemType Directory -Force (Split-Path $link) | Out-Null
    New-Item -ItemType Junction -Path $link -Target $target | Out-Null
    Write-Output "linked: $link -> $target"
}

# 1. Git metadata
$gitDir = Join-Path $env:USERPROFILE ".ultron\git\AGENT-ULTRON-BINDAL.git"
if (-not (Test-Path (Join-Path $gitDir "HEAD"))) {
    Write-Output "rebuilding Git metadata from GitHub in $gitDir"
    git init --quiet --bare $gitDir  # the folder itself is the Git dir; then marked non-bare
    git --git-dir=$gitDir config core.bare false
    git --git-dir=$gitDir remote add origin $repoUrl
    git --git-dir=$gitDir fetch --quiet origin
    git --git-dir=$gitDir symbolic-ref HEAD refs/heads/main
    git --git-dir=$gitDir update-ref refs/heads/main refs/remotes/origin/main
    git --git-dir=$gitDir branch --quiet --set-upstream-to=origin/main main
    # index from the commit; the working files on Drive stay as they are (local edits show as changes)
    git --git-dir=$gitDir --work-tree=$root reset --quiet --mixed main
    if ($LASTEXITCODE -ne 0) { Write-Error "git failed while rebuilding $gitDir" }
}
Set-Junction "C:\ProgramData\Ultron\git\AGENT-ULTRON-BINDAL.git" $gitDir

# 2. Claude Code memory on Drive
$memDrive = Join-Path (Split-Path $root) "AGENT-MEMORY\AGENT-ULTRON-BINDAL"
New-Item -ItemType Directory -Force $memDrive | Out-Null
$key = ($root -replace '[:\\/ ]', '-')
$memLocal = Join-Path $env:USERPROFILE ".claude\projects\$key\memory"
$item = Get-Item $memLocal -Force -ErrorAction SilentlyContinue
if ($item -and $item.LinkType -ne "Junction") {
    # notes written on this PC before the junction: keep them on Drive (Drive's copy wins a clash)
    Get-ChildItem $memLocal -File | Where-Object { $_.Name -ne "desktop.ini" } | ForEach-Object {
        $dest = Join-Path $memDrive $_.Name
        if (-not (Test-Path $dest)) { Copy-Item $_.FullName $dest }
    }
    Rename-Item $memLocal "memory.local-backup-$(Get-Date -Format yyyyMMddHHmmss)"
}
Set-Junction $memLocal $memDrive

# 3. Python venv
$venv = Join-Path $env:USERPROFILE ".ultron\venv"
if (Get-Command uv -ErrorAction SilentlyContinue) {
    $env:UV_PROJECT_ENVIRONMENT = $venv
    Push-Location $root
    try {
        uv sync --all-extras --frozen --quiet
        uv pip install --quiet --python (Join-Path $venv "Scripts\python.exe") pytest ruff
    } finally { Pop-Location }
    Write-Output "venv: $venv"
} else {
    Write-Output "uv not found: install it (https://docs.astral.sh/uv/) and run this again for the venv"
}

git -C $root status --short --branch | Select-Object -First 1
