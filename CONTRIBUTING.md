# Contributing to GodotMaker

Thank you for your interest in contributing to GodotMaker! This guide will help you get started.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Contribution Licensing

GodotMaker is licensed under the Business Source License 1.1 (see [LICENSE](LICENSE)). By submitting a contribution (for example, by opening a pull request), you confirm that you have the right to submit it, and you grant the project the right to use and redistribute your contribution as part of GodotMaker under that same license, including its eventual conversion to the Change License.

## How to Contribute

### Reporting Bugs

1. Search [existing issues](https://github.com/RandallLiuXin/GodotMaker/issues) to avoid duplicates.
2. Use the **Bug Report** issue template.
3. Include: Godot version, OS, steps to reproduce, expected vs actual behavior.

### Suggesting Features

1. Open an issue using the **Feature Request** template.
2. Describe the use case and why it benefits the project.

### Submitting Pull Requests

1. Fork the repo and create a branch from `main`.
2. Follow the coding conventions below.
3. Write or update tests for your changes.
4. For performance-sensitive changes, run benchmarks and include the results in the PR description.
5. Run the [local validation pipeline](#local-validation) before opening a PR.
6. Follow the [release-note entry contract](#release-note-entries).
7. Open a PR against `main` using the [PR template](.github/PULL_REQUEST_TEMPLATE.md).

## Development Setup

### Prerequisites

- Python 3.10+
- Node.js 22+
- Godot 4.5+
- Git and Bash (use Git Bash on Windows for the repository hook scripts)
- [gitleaks](https://github.com/gitleaks-io/gitleaks) (for secret scanning)

### Getting Started

```bash
git clone https://github.com/RandallLiuXin/GodotMaker.git
cd GodotMaker

# Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate

# Install the Python dependencies used by CI and the documentation build
python -m pip install pytest ruff==0.15.22 -r tools/requirements.txt
python -m pip install mkdocs-material mkdocs-static-i18n

# Install the repository hooks
bash scripts/install-hooks.sh
```

Confirm the frozen minimum tool versions before validating:

```bash
python --version
node --version
godot --version
gitleaks version
```

On Windows PowerShell, activate the virtual environment with
`.\.venv\Scripts\Activate.ps1`; run `scripts/install-hooks.sh` from Git Bash.

## Local Validation

From a clean checkout with the development dependencies installed, run:

```bash
# Python lint and test gates
ruff check .
python -m pytest --tb=short

# Documentation gates
python tools/check_doc_i18n.py --base origin/main --head HEAD
mkdocs build

# Secret-scan gate
gitleaks detect --source . --log-opts="origin/main..HEAD" --config .gitleaks.toml
```

Use `python tools/check_doc_i18n.py --staged` while preparing an uncommitted
documentation change. `python -m pytest tests/ -q` is the concise equivalent
used when a full-suite result is needed without CI's traceback formatting.

### Git Hook Order

`bash scripts/install-hooks.sh` installs the executable scripts under
`scripts/` without changing their behavior:

1. `pre-commit` runs Ruff on staged Python files when Ruff is installed.
2. `pre-commit` runs `python tools/check_doc_i18n.py --staged`.
3. `pre-commit` runs `gitleaks protect --staged` when Gitleaks is installed.
4. `pre-push` runs `ruff check .`, then `python -m pytest --tb=short`, when
   those tools are available.

The hooks warn and skip optional local tools that are missing. CI does not
skip its corresponding gates, so install every dependency listed above.

### Pull Request CI Gates

The executable definitions remain authoritative; this table records what a
contributor should expect.

| Workflow source | Gate | Executed validation |
| --- | --- | --- |
| `.github/workflows/ci.yml` | Doc i18n | Changed user-facing English docs include their Chinese mirrors. |
| `.github/workflows/ci.yml` | Lint Python | Ruff 0.15.22 runs `ruff check .`. |
| `.github/workflows/ci.yml` | Test Python | Python 3.12 runs `pytest --tb=short` on Ubuntu, Windows, and macOS. |
| `.github/workflows/ci.yml` | Secret Scan | The Gitleaks action scans for secrets. |
| `.github/workflows/docs.yml` | Build Docs | Documentation changes run `mkdocs build`. |

The supported contributor baseline is Python 3.10+ even though CI currently
executes the test matrix with Python 3.12.

## Release-note Entries

This section is the single complete source of truth for contributor rules for
[`docs/update/next.md`](docs/update/next.md). Other templates and release docs
must link here instead of copying these rules.

A PR that changes user-facing behavior, release content, dependencies, or
developer workflow must add a bullet under the appropriate heading in
`docs/update/next.md`. A docs-only typo fix or maintenance-only PR with no
release-note value may omit the entry. Contributors do not edit
`CHANGELOG.md`; the release owner updates it during release preparation.

- Write one sentence per bullet; split independent changes into separate bullets.
- Describe user-facing intent, not incident dates, internal project or test names,
  or debugging history.
- Use `(WIP)` only when the shipped change itself is incomplete.
- Use a Keep a Changelog category such as `Added`, `Changed`, `Fixed`, or
  `Removed`; add another category only when none fits.
- Follow the archived release-note format:
  `- Brief description of the change (#PR_NUMBER) — @author.`

## Coding Conventions

### GDScript / C#

- Follow the [GDScript style guide](https://docs.godotengine.org/en/stable/tutorials/scripting/gdscript/gdscript_styleguide.html).
- Code and comments in **English**.
- ECS systems must declare `reads`, `writes`, `creates_node`, `requires_node` metadata.
- Physics callbacks must never manipulate the node tree directly — use `DestroyTag` + `set_deferred`.

### Python (tools/)

- Follow PEP 8.
- Type hints encouraged.
- Tests in `tests/` using pytest.

### Commit Messages

- Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Keep the first line under 72 characters.
- Reference related issues: `Fixes #123`.

## Branch Strategy

- `main` — stable, always passing CI.
- Feature branches: `feat/short-description`.
- Bug fix branches: `fix/short-description`.

## Review Process

1. All PRs require at least one review.
2. CI must pass before merge.
3. Performance-sensitive PRs must include benchmark data in the PR description.

## Questions?

Open a [Discussion](https://github.com/RandallLiuXin/GodotMaker/discussions) or file an issue.
