param(
    [ValidateSet("start", "stop")]
    [string]$Action = "start",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$HermesArgs
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$HermesDir = Join-Path $Root "Hermes_agent"
$HermesExe = Join-Path $HermesDir ".venv\Scripts\hermes.exe"
$OpenNotebookEnv = Join-Path $Root "opennotebook\.env"
$env:HERMES_HOME = Join-Path $env:LOCALAPPDATA "hermes"

function Start-HermesAgent {
    if (-not (Test-Path -LiteralPath $HermesExe)) {
        throw "Hermes executable not found: $HermesExe. Create the virtual environment first."
    }

    if (Test-Path -LiteralPath $OpenNotebookEnv) {
        foreach ($line in Get-Content -LiteralPath $OpenNotebookEnv -Encoding UTF8) {
            if ($line -match '^\s*#' -or $line -notmatch '=') {
                continue
            }
            $parts = $line -split '=', 2
            $key = $parts[0].Trim()
            $value = $parts[1]
            if ($key -eq 'OPEN_NOTEBOOK_PASSWORD') {
                $env:OPEN_NOTEBOOK_PASSWORD = $value
            }
        }
        $env:OPEN_NOTEBOOK_URL = 'http://localhost:5055'
    }

    Set-Location -LiteralPath $HermesDir
    Write-Host "Starting Hermes Agent..." -ForegroundColor Cyan
    & $HermesExe @HermesArgs
    Write-Host ""
    Write-Host "Hermes exited. You can close this tab." -ForegroundColor Yellow
}

function Stop-HermesAgent {
    if (-not (Test-Path -LiteralPath $HermesDir -PathType Container)) {
        throw "Hermes directory not found: $HermesDir"
    }

    $needle = (Resolve-Path -LiteralPath $HermesDir).Path.ToLowerInvariant()
    $names = @('hermes.exe', 'python.exe', 'pythonw.exe', 'powershell.exe', 'pwsh.exe', 'node.exe', 'cmd.exe')
    $matches = Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $PID -and
        $_.CommandLine -and
        ($names -contains $_.Name.ToLowerInvariant()) -and
        $_.CommandLine.ToLowerInvariant().Contains($needle)
    }

    if (-not $matches) {
        Write-Host "No running Hermes process found for: $HermesDir"
        return
    }

    foreach ($process in $matches) {
        Write-Host ("Stopping " + $process.Name + " PID " + $process.ProcessId)
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
        } catch {
            Write-Warning ("Could not stop PID " + $process.ProcessId + ": " + $_.Exception.Message)
        }
    }
    Write-Host "Hermes stop command finished."
}

if ($Action -eq "start") {
    Start-HermesAgent
} else {
    Stop-HermesAgent
}
