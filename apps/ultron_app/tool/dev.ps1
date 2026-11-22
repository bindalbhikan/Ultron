param(
    [ValidateSet('preview', 'analyze', 'test', 'windows', 'web-build')]
    [string]$Action = 'preview'
)

$ErrorActionPreference = 'Stop'
$appDirectory = Split-Path -Parent $PSScriptRoot
$flutterCommand = Get-Command flutter -ErrorAction SilentlyContinue
$flutterExecutable = if ($flutterCommand) { $flutterCommand.Source } else { Join-Path $env:USERPROFILE '.ultron/tools/flutter/bin/flutter.bat' }
if (-not (Test-Path -LiteralPath $flutterExecutable -PathType Leaf)) {
    throw 'Install the Flutter SDK pinned in .flutter-version and add it to PATH.'
}

$workingDirectory = $appDirectory
if ($Action -in @('preview', 'windows', 'web-build')) {
    # Build in a fresh local directory: Drive's desktop.ini files can race Flutter asset copies.
    $buildBaseDirectory = [System.IO.Path]::GetFullPath((Join-Path $env:USERPROFILE '.ultron/build'))
    $workingDirectory = [System.IO.Path]::GetFullPath((Join-Path $buildBaseDirectory ('ultron-frontend-' + [guid]::NewGuid().ToString('N'))))
    if (-not $workingDirectory.StartsWith($buildBaseDirectory + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Build workspace is outside its intended local directory.'
    }
    New-Item -ItemType Directory -Path $workingDirectory -Force | Out-Null
    & robocopy $appDirectory $workingDirectory /E /XD .dart_tool build .idea .git /XF desktop.ini local.properties *.iml /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw 'Copying the frontend to its local build workspace failed.' }
    Write-Host "Local build workspace: $workingDirectory"
}

Push-Location -LiteralPath $workingDirectory
try {
    & $flutterExecutable pub get --enforce-lockfile
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    switch ($Action) {
        'preview' { & $flutterExecutable run -d web-server --web-hostname 127.0.0.1 --web-port 8788 }
        'analyze' { & $flutterExecutable analyze }
        'test' { & $flutterExecutable test }
        'windows' { & $flutterExecutable run -d windows }
        'web-build' { & $flutterExecutable build web --release }
    }
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
