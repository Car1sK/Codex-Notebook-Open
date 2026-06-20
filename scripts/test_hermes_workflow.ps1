$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$PythonExe = Join-Path $Root "Hermes_agent\.venv\Scripts\python.exe"
$Runner = Join-Path $Root "scripts\invoke_process.py"
$Delegator = Join-Path $Root "delegate_to_hermes.ps1"
$Temp = Join-Path ([System.IO.Path]::GetTempPath()) ("hermes-workflow-test-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $Temp | Out-Null

function Assert-Equal {
    param($Actual, $Expected, [string]$Message)
    if ($Actual -ne $Expected) {
        throw "$Message Expected '$Expected', got '$Actual'."
    }
}

try {
    $commandPath = Join-Path $Temp "command.ps1"
    $stdoutPath = Join-Path $Temp "stdout.txt"
    $stderrPath = Join-Path $Temp "stderr.txt"

    Set-Content -LiteralPath $commandPath -Value "Write-Output 'captured-ok'" -Encoding UTF8
    & $PythonExe $Runner --cwd $Temp --stdout-file $stdoutPath --stderr-file $stderrPath --timeout 10 --command-file $commandPath
    Assert-Equal $LASTEXITCODE 0 "Successful process exit code mismatch."
    Assert-Equal (Get-Content -Raw -LiteralPath $stdoutPath).Trim() "captured-ok" "Standard output was not captured."

    Set-Content -LiteralPath $commandPath -Value "if (`$env:PYTHONHOME -or `$env:UV_INTERNAL__PYTHONHOME) { exit 9 }" -Encoding UTF8
    & $PythonExe $Runner --cwd $Temp --stdout-file $stdoutPath --stderr-file $stderrPath --timeout 10 --command-file $commandPath
    Assert-Equal $LASTEXITCODE 0 "Verification process inherited the runner's Python home."

    Set-Content -LiteralPath $commandPath -Value "Write-Error 'expected-failure'" -Encoding UTF8
    & $PythonExe $Runner --cwd $Temp --stdout-file $stdoutPath --stderr-file $stderrPath --timeout 10 --command-file $commandPath
    if ($LASTEXITCODE -eq 0) { throw "Failing process was incorrectly accepted." }

    Set-Content -LiteralPath $commandPath -Value "Start-Sleep -Seconds 3" -Encoding UTF8
    & $PythonExe $Runner --cwd $Temp --stdout-file $stdoutPath --stderr-file $stderrPath --timeout 1 --command-file $commandPath
    Assert-Equal $LASTEXITCODE 124 "Timeout exit code mismatch."

    $delegatorText = Get-Content -Raw -LiteralPath $Delegator
    foreach ($required in @(
        '[ValidateSet("simple", "medium", "specialist")]',
        'AllowedPaths is required for implementation tasks.',
        'repository-root scope is forbidden.',
        'VerifyCommand is required for implementation tasks.',
        'failed_codex_takeover_required',
        'Hermes gates passed; Codex review is still required.'
    )) {
        if (-not $delegatorText.Contains($required)) {
            throw "Delegation workflow is missing required gate text: $required"
        }
    }

    Write-Output "Hermes workflow deterministic tests passed."
} finally {
    Remove-Item -LiteralPath $Temp -Recurse -Force -ErrorAction SilentlyContinue
}
