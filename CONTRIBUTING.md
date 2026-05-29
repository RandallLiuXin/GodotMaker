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
5. Run the full validation pipeline locally:
   ```bash
   # Run tests
   python -m pytest

   # Run gdUnit4 for Godot project changes
   godot --headless --path . -s res://addons/gdUnit4/bin/GdUnitCmdTool.gd --add res://test/ --ignoreHeadlessMode

   # Gitleaks (runs automatically via pre-commit hook)
   gitleaks detect --source . --config .gitleaks.toml
   ```
6. Add a changelog entry to [`docs/update/next.md`](docs/update/next.md) describing your change. Rules:
   - **One sentence per bullet.** If you can't fit it, your bullet is doing two things — split it.
   - **Describe user-facing intent, not the investigation behind it.** No incident dates, no internal project / test names, no debugging narrative. Past `vX.Y.Z.md` archives are the format reference.
   - **Use `(WIP)` only when the change itself is incomplete**. The prefix exists so the release-prep agent doesn't promote unfinished work into a tagged release — don't dilute it.
7. Open a PR against `main` using the [PR template](.github/PULL_REQUEST_TEMPLATE.md).

## Development Setup

### Prerequisites

- Godot 4.x (with .NET support recommended)
- Python 3.10+
- .NET SDK 8.0+
- [gitleaks](https://github.com/gitleaks-io/gitleaks) (for secret scanning)

### Getting Started

```bash
git clone https://github.com/RandallLiuXin/GodotMaker.git
cd GodotMaker

# Install git hooks (gitleaks pre-commit)
bash scripts/install-hooks.sh

# Install development dependencies used by CI
python -m pip install pytest ruff mkdocs mkdocs-material

# Optional: install asset/API provider dependencies when working on tools/
python -m pip install -r tools/requirements.txt
```

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
