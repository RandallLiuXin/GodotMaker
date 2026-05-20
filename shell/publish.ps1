# Publish GodotMaker skills into a target Godot project directory.
# Usage: .\shell\publish.ps1 [-Force|--force] [--no-config-review] [-Agent claude-code|codex|--agent <agent>] <target_godot_project_dir>
#
# On upgrade, compares VERSION against the target's .godotmaker/version:
#   PATCH  -> auto-proceed
#   MINOR  -> show changelog, prompt for confirmation
#   MAJOR  -> strong warning, prompt for confirmation
# Use -Force (or --force) to skip confirmation prompts and allow downgrades.
#
# Thin wrapper - all logic is in tools/publish.py.
# KEEP IN SYNC with publish.sh (Linux/macOS equivalent)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Script = Join-Path $RepoRoot "tools\publish.py"

# Parse args manually to accept both PowerShell-style and POSIX-style flags.
$ForceFlag = $false
$NoConfigReview = $false
$Agent = $null
$Target = $null

for ($i = 0; $i -lt $args.Count; $i++) {
    $a = $args[$i]
    if ($a -eq "-Force" -or $a -eq "--force") {
        $ForceFlag = $true
    } elseif ($a -eq "--no-config-review") {
        $NoConfigReview = $true
    } elseif ($a -eq "-Agent" -or $a -eq "--agent") {
        $i += 1
        if ($i -ge $args.Count) {
            Write-Host "Missing value for $a"
            exit 1
        }
        $Agent = $args[$i]
    } elseif (-not $Target) {
        $Target = $a
    }
}

if (-not $Target) {
    Write-Host "Usage: .\shell\publish.ps1 [-Force|--force] [--no-config-review] [-Agent claude-code|codex|--agent <agent>] <target_godot_project_dir>"
    exit 1
}

$pyArgs = @($Script)
if ($ForceFlag) { $pyArgs += "--force" }
if ($NoConfigReview) { $pyArgs += "--no-config-review" }
if ($Agent) { $pyArgs += @("--agent", $Agent) }
$pyArgs += $Target

& python @pyArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
