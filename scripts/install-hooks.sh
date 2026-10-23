#!/usr/bin/env bash
# Install git hooks for GodotMaker development
# Usage: bash scripts/install-hooks.sh

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

echo "Installing git hooks..."

# Install pre-commit hook (staged Ruff + doc i18n + Gitleaks)
PRECOMMIT_SRC="$REPO_ROOT/scripts/pre-commit"
PRECOMMIT_DST="$HOOKS_DIR/pre-commit"

if [ -f "$PRECOMMIT_DST" ] && [ ! -L "$PRECOMMIT_DST" ]; then
    echo "  Backing up existing pre-commit hook to pre-commit.bak"
    cp "$PRECOMMIT_DST" "$PRECOMMIT_DST.bak"
fi

ln -sf ../../scripts/pre-commit "$PRECOMMIT_DST"
echo "  Installed pre-commit hook as symlink (ruff lint + docs i18n + gitleaks secret scan)"

# Verify ruff
if command -v ruff &> /dev/null; then
    echo "  ruff found: $(ruff --version)"
else
    echo "  WARNING: ruff not installed. Hook will skip lint."
    echo "  Install: pip install ruff"
fi

# Verify gitleaks
if command -v gitleaks &> /dev/null; then
    echo "  gitleaks found: $(gitleaks version)"
else
    echo "  WARNING: gitleaks not installed. Hook will skip scanning."
    echo "  Install: https://github.com/gitleaks-io/gitleaks#installing"
fi

# Install pre-push hook (CI-equivalent Ruff + Pytest checks)
PREPUSH_SRC="$REPO_ROOT/scripts/pre-push"
PREPUSH_DST="$HOOKS_DIR/pre-push"

if [ -f "$PREPUSH_DST" ] && [ ! -L "$PREPUSH_DST" ]; then
    echo "  Backing up existing pre-push hook to pre-push.bak"
    cp "$PREPUSH_DST" "$PREPUSH_DST.bak"
fi

ln -sf ../../scripts/pre-push "$PREPUSH_DST"
echo "  Installed pre-push hook as symlink (CI-equivalent: ruff + pytest)"

echo "Done. Git hooks installed successfully."
