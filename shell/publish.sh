#!/usr/bin/env bash
# Publish GodotMaker skills into a target Godot project directory.
# Usage: bash shell/publish.sh [--force] [--no-config-review] [--agent claude-code|codex] <target_godot_project_dir>
#
# On upgrade, compares VERSION against the target's .godotmaker/version:
#   PATCH  -> auto-proceed
#   MINOR  -> show changelog, prompt for confirmation
#   MAJOR  -> strong warning, prompt for confirmation
# Use --force to skip confirmation prompts and allow downgrades.
#
# Thin wrapper — all logic is in tools/publish.py.
# KEEP IN SYNC with publish.ps1 (Windows PowerShell equivalent)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Detect python
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "Error: Python 3 is required. Install from https://python.org"
    exit 1
fi

exec "$PYTHON" "$REPO_ROOT/tools/publish.py" "$@"
