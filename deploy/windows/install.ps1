# Windows: install the agent in a virtualenv and run it as a scheduled task that starts at logon
# and restarts when it stops.
#   cd <the folder with agent.toml and .env>
#   powershell -ExecutionPolicy Bypass -File <Ultron>\deploy\windows\install.ps1   ($env:ULTRON_SPEC for another copy)
$ErrorActionPreference = "Stop"
$Dir = (Get-Location).Path
$Root = (Resolve-Path "$PSScriptRoot\..\..").Path      # the Ultron checkout
$Spec = if ($env:ULTRON_SPEC) { $env:ULTRON_SPEC } else { "${Root}[full]" }
if (-not (Test-Path "$Dir\agent.toml")) { throw "run this in the folder that holds agent.toml" }
if (-not (Test-Path "$Dir\.env")) { Write-Host "note: no .env here yet - put the secrets in $Dir\.env (see Ultron's README.md)" }

$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }   # works in Windows PowerShell 5.1 too
& $py -m venv .venv
& "$Dir\.venv\Scripts\python.exe" -m pip install --upgrade pip | Out-Null
& "$Dir\.venv\Scripts\pip.exe" install "$Spec"
& "$Dir\.venv\Scripts\ultron.exe" check

$action = New-ScheduledTaskAction -Execute "$PSScriptRoot\run_agent.bat" -WorkingDirectory $Dir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName "Ultron" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName "Ultron"
Write-Host "running. log: $Dir\output\ultron.log   stop: Stop-ScheduledTask Ultron"
