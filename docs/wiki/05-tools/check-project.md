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
| `--ecs` | The selected ECS backend is inspectable; GDScript/gecs projects have Component and System files |
| `--tests` | The selected test backend is inspectable; GDScript projects use gdUnit4 coverage and C#/.NET projects use the configured project-relative .NET test target |
| `--e2e` | The godot-e2e plugin is enabled; `e2e/` has real test functions, not placeholders |
| `--plan` | `PLAN.md` and `STRUCTURE.md` exist with the right sections |
| `--mcp` | The `godot-mcp` server is registered in `.mcp.json` |
| `--all` | All of the above |

## What it catches

**Build readiness** — confirms `project.godot` is present and structurally
valid, required addons have the expected addon-only shape, git `HEAD`
resolves, and `<godot_path> --headless --quit` has no blocking diagnostics.
For the C# backend, `<godot_path> --version` must also report a Mono/.NET build;
the standard non-.NET Godot executable is not accepted. Godot shutdown notes
are reported separately; other Godot diagnostics fail the check.


**ECS setup** — confirms that the selected backend has an inspectable ECS
shape. For GDScript/gecs projects, this means `addons/gecs/` is installed and
game code has files that `extend Component` and `extend System`. For the
C#/.NET backend, C# ECS static verification is N/A until a C# scanner is
implemented; do not treat the GDScript scan as authoritative for C# projects.

**Unit test coverage** — uses the configured unit test backend. GDScript
projects check that every System file has a corresponding gdUnit test file.
The C#/.NET backend uses `unit_test_backend`, an optional project-relative
`dotnet_target`, and standard `dotnet test` results instead of gdUnit4 XML.

**C#/.NET backend** — recognizes existing Godot .NET projects through
`language_backend`, `unit_test_backend`, optional project-relative `dotnet_target`,
and optional project-relative `godot_csharp_project` in
`.godotmaker/config.yaml`. C# ECS static verification is N/A in the current
release; build and unit verification are the authoritative C# checks.

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
