param(
    [Parameter(Mandatory = $true)]
    [string]$TargetRepo,

    [switch]$IncludeProjectMcp,

    [switch]$ReloadCursorWindow
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[bootLightRAG] $Message" -ForegroundColor Cyan
}

function Invoke-CursorReloadWindow {
    Write-Step "Attempting Cursor window reload..."

    $ahkCandidates = @(
        "C:\Users\User\AppData\Local\Programs\AutoHotkey\v2\AutoHotkey64.exe",
        "C:\Users\User\AppData\Local\Programs\AutoHotkey\v2\AutoHotkey32.exe"
    )
    $ahkExe = $ahkCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

    if (-not $ahkExe) {
        Write-Host "[bootLightRAG] AutoHotkey not found, skip auto reload. Please run: Developer: Reload Window" -ForegroundColor Yellow
        return
    }

    $tmpAhk = Join-Path $env:TEMP "cursor-reload-window.ahk"
    $ahkScript = @'
#Requires AutoHotkey v2.0
SetTitleMatchMode "RegEx"

if WinExist("ahk_exe Antigravity.exe") {
    WinActivate("ahk_exe Antigravity.exe")
} else if WinExist("ahk_exe Cursor.exe") {
    WinActivate("ahk_exe Cursor.exe")
}

Sleep 250
Send("^+p")
Sleep 250
SendText(">workbench.action.reloadWindow")
Sleep 120
Send("{Enter}")
'@
    Set-Content -Path $tmpAhk -Value $ahkScript -Encoding UTF8
    Start-Process -FilePath $ahkExe -ArgumentList "`"$tmpAhk`"" -WindowStyle Hidden
    Write-Step "Reload command sent to Cursor."
}

function Copy-IfExists {
    param(
        [string]$SourcePath,
        [string]$DestinationPath,
        [switch]$Recurse
    )

    if (-not (Test-Path $SourcePath)) {
        throw "Source not found: $SourcePath"
    }

    $srcResolved = (Resolve-Path -Path $SourcePath).Path
    $destCandidate = Join-Path $DestinationPath (Split-Path -Path $SourcePath -Leaf)
    $destResolved = $null
    if (Test-Path $destCandidate) {
        $destResolved = (Resolve-Path -Path $destCandidate).Path
    }

    if ($destResolved -and ($srcResolved -ieq $destResolved)) {
        Write-Step "Skip self-copy: $srcResolved"
        return
    }

    if ($Recurse) {
        Copy-Item -Path $SourcePath -Destination $DestinationPath -Recurse -Force
    }
    else {
        Copy-Item -Path $SourcePath -Destination $DestinationPath -Force
    }
}

$targetRepoResolved = (Resolve-Path -Path $TargetRepo).Path
$sourceRoot = $PSScriptRoot
$sourceCursor = Join-Path $sourceRoot ".cursor"
$targetCursor = Join-Path $targetRepoResolved ".cursor"
$targetRules = Join-Path $targetCursor "rules"
$targetSkills = Join-Path $targetCursor "skills"

if (-not (Test-Path $sourceCursor)) {
    throw "Source .cursor folder not found in: $sourceRoot"
}

Write-Step "Target repo: $targetRepoResolved"
Write-Step "Source repo: $sourceRoot"

New-Item -ItemType Directory -Force -Path $targetCursor | Out-Null
New-Item -ItemType Directory -Force -Path $targetRules | Out-Null
New-Item -ItemType Directory -Force -Path $targetSkills | Out-Null

$ruleFiles = @(
    "lightrag-auto-lookup.mdc",
    "lightrag-shortcuts.mdc",
    "lightrag-response-format.mdc"
)

foreach ($rule in $ruleFiles) {
    $src = Join-Path $sourceCursor ("rules\" + $rule)
    Write-Step "Copy rule: $rule"
    Copy-IfExists -SourcePath $src -DestinationPath $targetRules
}

$skillDirs = @(
    "lightrag-chatops",
    "lightrag-ingestion-operator",
    "lightrag-research-loop"
)

foreach ($skillDir in $skillDirs) {
    $src = Join-Path $sourceCursor ("skills\" + $skillDir)
    Write-Step "Copy skill: $skillDir"
    Copy-IfExists -SourcePath $src -DestinationPath $targetSkills -Recurse
}

if ($IncludeProjectMcp) {
    $srcMcp = Join-Path $sourceCursor "mcp.json"
    $dstMcp = Join-Path $targetCursor "mcp.json"
    Write-Step "Copy project MCP config: .cursor/mcp.json"
    if ((Test-Path $srcMcp) -and (Test-Path $dstMcp) -and ((Resolve-Path $srcMcp).Path -ieq (Resolve-Path $dstMcp).Path)) {
        Write-Step "Skip self-copy: $dstMcp"
    }
    else {
        Copy-IfExists -SourcePath $srcMcp -DestinationPath $dstMcp
    }
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "Copied LightRAG Cursor setup to: $targetRepoResolved" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1) Open target repo in Cursor"
Write-Host "2) Reload window (Command Palette -> Developer: Reload Window)"
Write-Host "3) Test in chat: @lightrag status"
if (-not $IncludeProjectMcp) {
    Write-Host "4) Optional: re-run with -IncludeProjectMcp to copy .cursor/mcp.json"
}

if ($ReloadCursorWindow) {
    Invoke-CursorReloadWindow
}
