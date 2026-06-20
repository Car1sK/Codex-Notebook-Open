param(
    [string]$Prompt = "",
    [string]$PromptFile = "",
    [Parameter(Mandatory = $true)]
    [ValidateSet("simple", "medium", "specialist")]
    [string]$TaskClass,
    [string]$WorkDir = "",
    [switch]$AllowEdits,
    [string[]]$AllowedPaths = @(),
    [string]$VerifyCommand = "",
    [ValidateRange(60, 1800)]
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSCommandPath
$HermesDir = Join-Path $Root "Hermes_agent"
$HermesExe = Join-Path $HermesDir ".venv\Scripts\hermes.exe"
$PythonExe = Join-Path $HermesDir ".venv\Scripts\python.exe"
$ProcessRunner = Join-Path $Root "scripts\invoke_process.py"
$SimpleModel = "deepseek-v4-flash"
$ImplementationModel = "deepseek-v4-pro"
$ReviewerModel = "deepseek-v4-pro"

function Write-TextFile {
    param([string]$Path, [string]$Value)
    Set-Content -LiteralPath $Path -Value $Value -Encoding UTF8
}

function ConvertTo-ToolPath {
    param([string]$Path)
    return $Path.Replace('\', '/')
}

function Get-RepositorySnapshot {
    param([string]$Repository)

    $snapshot = @{}
    $files = & git -C $Repository ls-files --cached --others --exclude-standard
    if ($LASTEXITCODE -ne 0) {
        throw "WorkDir must be a Git repository: $Repository"
    }

    foreach ($relativePath in $files) {
        if ([string]::IsNullOrWhiteSpace($relativePath)) { continue }
        $fullPath = Join-Path $Repository $relativePath
        if (Test-Path -LiteralPath $fullPath -PathType Leaf) {
            $snapshot[$relativePath.Replace('/', '\')] = (Get-FileHash -Algorithm SHA256 -LiteralPath $fullPath).Hash
        }
    }
    return $snapshot
}

function Compare-Snapshots {
    param([hashtable]$Before, [hashtable]$After)

    $allPaths = @($Before.Keys) + @($After.Keys) | Sort-Object -Unique
    return @($allPaths | Where-Object {
        (-not $Before.ContainsKey($_)) -or
        (-not $After.ContainsKey($_)) -or
        ($Before[$_] -ne $After[$_])
    })
}

function Test-AllowedPath {
    param([string]$RelativePath, [string[]]$Scopes)

    $candidate = $RelativePath.Replace('/', '\').TrimStart('.','\')
    foreach ($scope in $Scopes) {
        $normalizedScope = $scope.Replace('/', '\').Trim().TrimStart('.','\').TrimEnd('\')
        if ($candidate -eq $normalizedScope -or $candidate.StartsWith($normalizedScope + '\', [StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

function Invoke-CapturedProcess {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [string]$PromptPath = "",
        [string]$CommandPath = "",
        [string]$Model = "",
        [string]$Provider = "",
        [int]$Timeout,
        [switch]$Hermes
    )

    $stdoutPath = Join-Path $OutDir "$Name.stdout.txt"
    $stderrPath = Join-Path $OutDir "$Name.stderr.txt"
    $runnerArgs = @(
        $ProcessRunner,
        "--cwd", $WorkingDirectory,
        "--stdout-file", $stdoutPath,
        "--stderr-file", $stderrPath,
        "--timeout", $Timeout
    )

    if ($Hermes) {
        $runnerArgs += @("--hermes-exe", $HermesExe, "--prompt-file", $PromptPath, "--model", $Model, "--provider", $Provider)
    } else {
        $runnerArgs += @("--command-file", $CommandPath)
    }

    & $PythonExe @runnerArgs
    $exitCode = $LASTEXITCODE
    $stdout = if (Test-Path -LiteralPath $stdoutPath) { Get-Content -Raw -LiteralPath $stdoutPath } else { "" }
    $stderr = if (Test-Path -LiteralPath $stderrPath) { Get-Content -Raw -LiteralPath $stderrPath } else { "" }

    [pscustomobject]@{
        Name = $Name
        ExitCode = $exitCode
        StdoutPath = $stdoutPath
        StderrPath = $stderrPath
        Stdout = $stdout
        Stderr = $stderr
    }
}

function Invoke-HermesPhase {
    param(
        [string]$Name,
        [string]$PhasePrompt,
        [string]$Model,
        [string]$Provider
    )

    $promptPath = Join-Path $OutDir "$Name.prompt.txt"
    Write-TextFile -Path $promptPath -Value $PhasePrompt
    $result = Invoke-CapturedProcess -Name $Name -WorkingDirectory $ResolvedWorkDir -PromptPath $promptPath -Model $Model -Provider $Provider -Timeout $TimeoutSeconds -Hermes
    if ($result.ExitCode -ne 0) {
        throw "$Name failed with exit code $($result.ExitCode). See $($result.StderrPath)"
    }
    if ([string]::IsNullOrWhiteSpace($result.Stdout)) {
        throw "$Name returned no response."
    }
    return $result
}

function Get-RequiredField {
    param([string]$Text, [string]$Field)
    $match = [regex]::Match($Text, "(?m)^" + [regex]::Escape($Field) + ":\s*(.+)$")
    if (-not $match.Success -or [string]::IsNullOrWhiteSpace($match.Groups[1].Value)) {
        throw "Missing required handoff field: $Field"
    }
    return $match.Groups[1].Value.Trim()
}

function Test-ImplementationHandoff {
    param([string]$Text)
    foreach ($field in @("CLASSIFICATION", "ROLE", "STATUS", "CHANGED_FILES", "ROOT_CAUSE_OR_RATIONALE", "VERIFICATION", "SUMMARY", "REMAINING_RISKS")) {
        $null = Get-RequiredField -Text $Text -Field $field
    }
    if ((Get-RequiredField -Text $Text -Field "STATUS") -ne "completed") {
        throw "Hermes did not report STATUS: completed."
    }
    if ((Get-RequiredField -Text $Text -Field "CLASSIFICATION") -ne $TaskClass) {
        throw "Hermes classification does not match the externally assigned task class."
    }
}

function Invoke-Verification {
    param([string]$Name)
    $commandPath = Join-Path $OutDir "$Name.command.ps1"
    Write-TextFile -Path $commandPath -Value $VerifyCommand
    return Invoke-CapturedProcess -Name $Name -WorkingDirectory $ResolvedWorkDir -CommandPath $commandPath -Timeout $TimeoutSeconds
}

function Assert-ScopedChanges {
    param([hashtable]$Baseline)
    $current = Get-RepositorySnapshot -Repository $ResolvedWorkDir
    $changed = Compare-Snapshots -Before $Baseline -After $current
    $outsideScope = @($changed | Where-Object { -not (Test-AllowedPath -RelativePath $_ -Scopes $AllowedPaths) })
    if ($outsideScope.Count -gt 0) {
        throw "Hermes changed files outside AllowedPaths: $($outsideScope -join ', ')"
    }
    if ($AllowEdits -and $changed.Count -eq 0) {
        throw "Hermes reported completion but produced no filesystem change."
    }
    Write-TextFile -Path (Join-Path $OutDir "actual_changed_files.txt") -Value ($changed -join "`r`n")
    return $changed
}

function Get-ReviewerVerdict {
    param([string]$Text)
    $verdict = Get-RequiredField -Text $Text -Field "VERDICT"
    if ($verdict -notin @("APPROVED", "CHANGES_REQUIRED", "BLOCKED")) {
        throw "Invalid reviewer verdict: $verdict"
    }
    $null = Get-RequiredField -Text $Text -Field "FINDINGS"
    $null = Get-RequiredField -Text $Text -Field "VERIFICATION_ASSESSMENT"
    $null = Get-RequiredField -Text $Text -Field "REMAINING_RISKS"
    return $verdict
}

if (-not (Test-Path -LiteralPath $HermesExe) -or -not (Test-Path -LiteralPath $PythonExe) -or -not (Test-Path -LiteralPath $ProcessRunner)) {
    throw "Hermes runtime or process runner is missing."
}

if ($PromptFile) {
    $Prompt = Get-Content -Raw -LiteralPath (Resolve-Path -LiteralPath $PromptFile).Path
}
if ([string]::IsNullOrWhiteSpace($Prompt)) {
    throw "Prompt or PromptFile is required."
}
if ([string]::IsNullOrWhiteSpace($WorkDir)) {
    throw "WorkDir is required."
}
if (-not $AllowEdits) {
    throw "Read-only work should remain with Codex; this workflow is for implementation tasks."
}
if ($AllowedPaths.Count -eq 0) {
    throw "AllowedPaths is required for implementation tasks."
}
foreach ($scope in $AllowedPaths) {
    if ($scope.Trim() -in @("", ".", "./", ".\", "/", "\")) {
        throw "AllowedPaths must name specific files or directories; repository-root scope is forbidden."
    }
}
if ([string]::IsNullOrWhiteSpace($VerifyCommand)) {
    throw "VerifyCommand is required for implementation tasks."
}

$ResolvedWorkDir = (Resolve-Path -LiteralPath $WorkDir).Path
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$OutDir = Join-Path $Root ".hermes_delegations\$Stamp"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$TaskPath = Join-Path $OutDir "task.txt"
Write-TextFile -Path $TaskPath -Value $Prompt
$Baseline = Get-RepositorySnapshot -Repository $ResolvedWorkDir
& git -C $ResolvedWorkDir status --short | Set-Content -LiteralPath (Join-Path $OutDir "baseline_status.txt") -Encoding UTF8
& git -C $ResolvedWorkDir diff --binary | Set-Content -LiteralPath (Join-Path $OutDir "baseline.patch") -Encoding UTF8

$planPath = Join-Path $OutDir "plan.md"
$ToolWorkDir = ConvertTo-ToolPath $ResolvedWorkDir
$ToolTaskPath = ConvertTo-ToolPath $TaskPath
$ToolPlanPath = ConvertTo-ToolPath $planPath
$implementationModel = if ($TaskClass -eq "simple") { $SimpleModel } else { $ImplementationModel }
$attempt = 1

try {
    if ($TaskClass -eq "simple") {
        Write-TextFile -Path $planPath -Value "Simple task: inspect relevant files, make the minimum scoped change, and run the requested focused verification."
    } else {
        $plannerPrompt = @"
You are the read-only planner in an externally enforced engineering workflow.
Do not edit files and do not delegate. Read repository instructions first.
Task class: $TaskClass
Workspace: $ToolWorkDir
Task file: $ToolTaskPath
Allowed paths: $($AllowedPaths -join ', ')
Required independent verification: $VerifyCommand

Inspect only relevant files. Produce the smallest executable plan with exact paths, assumptions grounded in local evidence, one verification check per step, and material risks. Do not propose optional work.
"@
        $planner = Invoke-HermesPhase -Name "01_planner" -PhasePrompt $plannerPrompt -Model $ImplementationModel -Provider "deepseek"
        Write-TextFile -Path $planPath -Value $planner.Stdout
    }

    $implementerPrompt = @"
You are the implementer in an externally enforced engineering workflow.
Do not reclassify, delegate, review your own work, commit, push, reset, clean, install dependencies, or touch files outside the allowed paths.
Read repository instructions, the task, and the accepted plan before editing.

Assigned classification: $TaskClass
Workspace: $ToolWorkDir
Task file: $ToolTaskPath
Plan file: $ToolPlanPath
Allowed paths: $($AllowedPaths -join ', ')
Required verification command: $VerifyCommand

First reproduce or establish the current behavior when practical. Implement the minimum complete change. Run the narrowest relevant checks. Do not claim success from code inspection alone.

Return plain text with exactly these single-line fields and no Markdown decoration:
CLASSIFICATION: $TaskClass
ROLE: implementer
STATUS: completed | blocked | failed
CHANGED_FILES: comma-separated paths, or none
ROOT_CAUSE_OR_RATIONALE: concrete evidence for why the change is correct
VERIFICATION: exact commands and observed results
SUMMARY: concise implementation result
REMAINING_RISKS: concrete items, or none
"@
    $implementation = Invoke-HermesPhase -Name "02_implementer" -PhasePrompt $implementerPrompt -Model $implementationModel -Provider "deepseek"
    Test-ImplementationHandoff -Text $implementation.Stdout
    $changedFiles = Assert-ScopedChanges -Baseline $Baseline
    $verification = Invoke-Verification -Name "03_verification"
    $changedFiles = Assert-ScopedChanges -Baseline $Baseline

    $reviewVerdict = "APPROVED"
    if ($TaskClass -ne "simple") {
        & git -C $ResolvedWorkDir diff --binary | Set-Content -LiteralPath (Join-Path $OutDir "candidate.patch") -Encoding UTF8
        $reviewPrompt = @"
You are the independent read-only reviewer in an externally enforced engineering workflow. Do not edit files or delegate.
Review the actual working-tree delta against the task and repository instructions. This is a fresh review session; do not trust the implementer's claims.

Workspace: $ToolWorkDir
Task file: $ToolTaskPath
Plan file: $ToolPlanPath
Implementation response: $(ConvertTo-ToolPath $implementation.StdoutPath)
Baseline patch: $(ConvertTo-ToolPath (Join-Path $OutDir 'baseline.patch'))
Candidate patch: $(ConvertTo-ToolPath (Join-Path $OutDir 'candidate.patch'))
Actual changed files: $($changedFiles -join ', ')
Independent verification stdout: $(ConvertTo-ToolPath $verification.StdoutPath)
Independent verification stderr: $(ConvertTo-ToolPath $verification.StderrPath)
Independent verification exit code: $($verification.ExitCode)

Check specification coverage, repository rules, correctness, scope, failure modes, and whether tests exercise the changed seam. Treat a failed verification command as CHANGES_REQUIRED. Do not approve based on the implementer's claims.

Return plain text with exactly these single-line fields and no Markdown decoration:
VERDICT: APPROVED | CHANGES_REQUIRED | BLOCKED
FINDINGS: actionable findings with paths, or none
VERIFICATION_ASSESSMENT: what the independent evidence proves or fails to prove
REMAINING_RISKS: concrete items, or none
"@
        $review = Invoke-HermesPhase -Name "04_reviewer" -PhasePrompt $reviewPrompt -Model $ReviewerModel -Provider "deepseek"
        $reviewVerdict = Get-ReviewerVerdict -Text $review.Stdout
    } elseif ($verification.ExitCode -ne 0) {
        $reviewVerdict = "CHANGES_REQUIRED"
    }

    if ($verification.ExitCode -ne 0 -or $reviewVerdict -ne "APPROVED") {
        $attempt = 2
        $repairPrompt = @"
You are the implementer performing the single permitted repair pass. Do not delegate or broaden scope.
Workspace: $ToolWorkDir
Task file: $ToolTaskPath
Plan file: $ToolPlanPath
Allowed paths: $($AllowedPaths -join ', ')
Previous implementation: $(ConvertTo-ToolPath $implementation.StdoutPath)
Independent verification stdout: $(ConvertTo-ToolPath $verification.StdoutPath)
Independent verification stderr: $(ConvertTo-ToolPath $verification.StderrPath)
Reviewer response: $(if ($TaskClass -ne 'simple') { ConvertTo-ToolPath $review.StdoutPath } else { 'not applicable' })

Fix only the evidenced failure. Rerun the focused check. If the evidence is insufficient, return STATUS: blocked instead of guessing.

Return plain text with exactly these single-line fields and no introductory text or Markdown decoration:
CLASSIFICATION: $TaskClass
ROLE: implementer
STATUS: completed | blocked | failed
CHANGED_FILES: comma-separated paths, or none
ROOT_CAUSE_OR_RATIONALE: concrete evidence for the repair
VERIFICATION: exact commands and observed results
SUMMARY: concise repair result
REMAINING_RISKS: concrete items, or none
"@
        $repair = Invoke-HermesPhase -Name "05_repair" -PhasePrompt $repairPrompt -Model $ImplementationModel -Provider "deepseek"
        Test-ImplementationHandoff -Text $repair.Stdout
        $changedFiles = Assert-ScopedChanges -Baseline $Baseline
        $verification = Invoke-Verification -Name "06_verification_after_repair"
        $changedFiles = Assert-ScopedChanges -Baseline $Baseline
        if ($verification.ExitCode -ne 0) {
            throw "Independent verification still fails after the single repair pass. Codex must take over."
        }

        if ($TaskClass -ne "simple") {
            & git -C $ResolvedWorkDir diff --binary | Set-Content -LiteralPath (Join-Path $OutDir "repaired_candidate.patch") -Encoding UTF8
            $finalReviewPrompt = @"
You are the independent final reviewer. This is the last review after one repair pass. Do not edit or delegate.
Workspace: $ToolWorkDir
Task file: $ToolTaskPath
Allowed paths: $($AllowedPaths -join ', ')
Repair response: $(ConvertTo-ToolPath $repair.StdoutPath)
Repaired candidate patch: $(ConvertTo-ToolPath (Join-Path $OutDir 'repaired_candidate.patch'))
Independent verification stdout: $(ConvertTo-ToolPath $verification.StdoutPath)
Independent verification stderr: $(ConvertTo-ToolPath $verification.StderrPath)
Independent verification exit code: $($verification.ExitCode)

Return plain text with exactly these single-line fields:
VERDICT: APPROVED | CHANGES_REQUIRED | BLOCKED
FINDINGS: actionable findings with paths, or none
VERIFICATION_ASSESSMENT: what the independent evidence proves or fails to prove
REMAINING_RISKS: concrete items, or none
"@
            $finalReview = Invoke-HermesPhase -Name "07_final_reviewer" -PhasePrompt $finalReviewPrompt -Model $ReviewerModel -Provider "deepseek"
            if ((Get-ReviewerVerdict -Text $finalReview.Stdout) -ne "APPROVED") {
                throw "Independent review still rejects the work after the single repair pass. Codex must take over."
            }
        }
    }

    $result = [ordered]@{
        status = "accepted_for_codex_review"
        task_class = $TaskClass
        implementation_model = $implementationModel
        reviewer_model = if ($TaskClass -eq "simple") { "Codex" } else { $ReviewerModel }
        attempts = $attempt
        changed_files = $changedFiles
        verification_exit_code = $verification.ExitCode
        artifact_directory = $OutDir
    }
    $result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutDir "result.json") -Encoding UTF8
    Write-Host "Hermes gates passed; Codex review is still required." -ForegroundColor Green
    Write-Host (Join-Path $OutDir "result.json")
} catch {
    $failure = [ordered]@{
        status = "failed_codex_takeover_required"
        task_class = $TaskClass
        attempts = $attempt
        reason = $_.Exception.Message
        artifact_directory = $OutDir
    }
    $failure | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutDir "result.json") -Encoding UTF8
    Write-Error "$($_.Exception.Message) Artifacts: $OutDir"
    exit 1
}
