# Check your project

`check_project.py` inspects a generated game project for missing files, broken structure, and other inconsistencies. Run this when a build is acting strange or before sealing a tag.

```bash
python tools/check_project.py /path/to/my-game
```

With no flags, all checks run. You can also run specific categories:

```bash
python tools/check_project.py /path/to/my-game --ecs --tests
python tools/check_project.py /path/to/my-game --all
```

## Category flags

| Flag | What it checks |
|------|---------------|
| `--build` | `project.godot` exists, required addons are installed, git `HEAD` resolves, and Godot headless parse has no blocking diagnostics |
| `--ecs` | The gecs addon is present; game code has Component and System files |
| `--tests` | The gdUnit4 addon is present; every System has a matching unit test file |
| `--e2e` | The godot-e2e plugin is enabled; `e2e/` has real test functions, not placeholders |
| `--plan` | `PLAN.md` and `STRUCTURE.md` exist with the right sections |
| `--mcp` | The `godot-mcp` server is registered in `.mcp.json` |
| `--all` | All of the above |

## What it catches

**Build readiness** — confirms `project.godot` is present and structurally
valid, required addons have the expected addon-only shape, git `HEAD`
resolves, and `<godot_path> --headless --quit` has no blocking diagnostics.
Godot shutdown notes are reported separately; other Godot diagnostics fail the
check.

**ECS setup** — confirms that `addons/gecs/` is installed and that your game actually has GDScript files that `extend Component` and `extend System`. A project with neither has not been built yet (or the build was interrupted).

**Unit test coverage** — checks that every System file has a corresponding test file. It looks for matches like `test_movement_system.gd`, `movement_system_test.gd`, or `testmovementsystem.gd`. Systems without tests are listed by name.

**End-to-end tests** — checks that `e2e/conftest.py` exists, that there are `test_*.py` files in the `e2e/` folder, and that those files contain real `def test_` functions and are not empty stubs. Placeholder files that are too short or contain "todo" / "stub" keywords trigger a warning.

**Planning documents** — confirms `PLAN.md` exists with task status markers (`pending`, `in_progress`, `completed`, etc.) and that `STRUCTURE.md` has a Component Registry and a System Schedule. These are the documents that guide `/gm-build` and `/gm-fixgap`.

**MCP registration** — checks that `.mcp.json` contains a `"godot"` server entry, which is what `publish.py` creates. Without it, Claude Code cannot send commands to the Godot editor.

## When to run it

- After a build that produced errors or unexpected behavior.
- Before running `/gm-finalize` to confirm the project is complete.
- When resuming a project after a long break, to see what state it is in.
- After manually adding or renaming files, to confirm nothing is broken.

## Reading the output

```
[PASS] project.godot exists
[FAIL] No System files found (files extending System)
[WARN] MEMORY.md not found (optional but recommended)
```

Failed checks are summarized at the end:

```
==================================================
Total: 18 checks
  PASS: 15
  FAIL: 2
  WARN: 1

Result: CHECKS FAILED
Failed checks:
  - No System files found (files extending System)
  - Systems without test files: movement_system, spawn_system
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | One or more checks failed |
| 2 | The project directory does not exist |
