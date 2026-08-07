---
name: gm-scaffold
description: |
  Scaffold a new Godot project: project.godot + addons + base directories +
  e2e/conftest.py + initial git commit. Lifetime-once role — runs only on
  fresh projects.
  Explicit invocation only — use /gm-scaffold.
disable-model-invocation: true
---

# GodotMaker Scaffold

$ARGUMENTS

You are scaffolding a brand-new Godot project. This is the **lifetime-once** foundation step: project.godot + addons + base directory layout + e2e/conftest.py + initial git commit. No game design happens here — that comes in `/gm-gdd`.

## Session Setup

**FIRST ACTION — before anything else:** Write `scaffold` to `.godotmaker/current_role`.

`session_start.py` deletes `.godotmaker/current_role` on every new session
(including `/clear`, restart, and resume) so a stale role from a previous
session can't grant unintended write permissions. That is why every gm-*
skill re-writes its role as the first action — if a session is interrupted
mid-scaffold and you don't re-issue `/gm-scaffold`, write hooks will start
denying file writes silently. Re-issuing the slash command re-establishes
the role.

## Resume Check

Read `.godotmaker/stage.jsonl` (treat as empty if missing) — each line is `{"role": X, "ts": Y}`. Find the **last event** in the file.

Scaffold is **lifetime-once** — its event gets cleared after each tag's finalize (stage.jsonl is truncated). So determine "already scaffolded" from project artifacts on disk, not the event log:

- If `project.godot` exists AND `git log` has at least one commit, first determine the backend:
  - Existing C#/.NET resume detection must not require `addons/gecs/` or `addons/gdUnit4/`. If `.godotmaker/config.yaml` records `language_backend: csharp`, or the project has existing `.sln` / `.csproj` Godot C# files, STOP and tell the user:
    > "Project is already scaffolded as an existing C#/.NET project. Recommended next: /gm-gdd."
  - For the GDScript/gecs backend, require `addons/gecs/` as part of the already-scaffolded check. If present, STOP and tell the user:
    > "Project is already scaffolded. Recommended next: /gm-gdd.
    > If you need to re-scaffold (rare — usually addon migrations are handled by `tools/publish.py`), just tell me."
- Otherwise → proceed.

## Hard Rules

1. **Do NOT design the game here.**
2. **Use fixed 2D defaults.** Use the project-scaffold default viewport (`1280x720`) and rendering method.
3. **Do NOT create Component/System stubs.**
4. **All addons MUST come from the active runtime's `config/addon_versions.json`** — do not guess versions.
5. **Initial git commit is mandatory and must include import metadata.** Run `<godot_path> --headless --import` before the commit and include generated `.uid` files.

## Scaffold Steps

### 1. Gather minimal inputs

Use `AskUserQuestion` to ask for:
- **Game name** (snake_case, used as project directory name)

Use 2D defaults. GodotMaker currently generates 2D games only; do not ask the
user to choose a dimension during scaffold.

Other settings (genre, art style, mechanics) are deferred to `/gm-gdd`.

### 1b. Recognize existing C#/.NET projects

If the target already contains a Godot .NET project (`*.sln`, `*.csproj`, or
Godot-generated C# project files), recognize the backend before creating any
new architecture:

- record `language_backend: csharp` in `.godotmaker/config.yaml` when the file
  exists and the project is clearly C#/.NET-owned
- keep `unit_test_backend: auto` unless the user explicitly selected a
  backend
- Do not generate .sln/.csproj or C# ECS architecture in this first scaffold
  pass
- do not create Component/System/test files; `/gm-gdd` and `/gm-build` own the
  architecture after the backend has been recorded

### 2a. Run project-scaffold skill

For empty or GDScript projects, invoke `.claude/skills/project-scaffold/SKILL.md`
with only the gathered game name. Use project-scaffold defaults for every other
template variable. Run only Steps 1, 2, and 3. Do not run genre adaptations.
For existing C#/.NET projects, skip GDScript starter architecture and preserve
existing `.sln`, `.csproj`, source, test, and scene layout. From Step 3's
template table, the GDScript branch fills just these four templates:

- `project.godot.tmpl` → `project.godot`
- `main_scene.tmpl` → `scenes/main.tscn`
- `world_scene.tmpl` → `scenes/game_world.tscn`
- `gitignore.tmpl` → `.gitignore`

That gives you the directory tree, an empty `Main` entry-point scene, the
gameplay scene placeholder, and a sensible `.gitignore`.

The remaining items in project-scaffold belong to other parts of the pipeline:

| project-scaffold concern | Owner |
|--------------------------|-------|
| Component / System / test files (with or without a Game Plan) | decomposer in `/gm-gdd` writes STRUCTURE.md first; workers in `/gm-build` create the actual backend-owned source files |
| Genre Adaptations — `[physics]` / `[input]` (Step 4) | `/gm-gdd` |
| Post-Scaffold publish (Step 5) | already done by `tools/publish.py` before scaffold runs |
| Addon install | step 2b below |

### 2b. Install backend-required addon-only directories

Install required addons from the active runtime's `config/addon_versions.json`.
Follow `project-scaffold/references/addons.md`, but choose the row by backend.

GDScript backend required result:

1. `addons/gecs/plugin.cfg`
2. `addons/gdUnit4/plugin.cfg`
3. `addons/gdUnit4/bin/GdUnitCmdTool.gd`
4. `addons/gdUnit4/src/core/runners/GdUnitTestCIRunner.gd`
5. `addons/godot_e2e/plugin.cfg`
6. `addons/godot_e2e/automation_server.gd`
7. no `addons/*/project.godot`

Existing C#/.NET backend required result:

1. `addons/godot_e2e/plugin.cfg`
2. `addons/godot_e2e/automation_server.gd`
3. no `addons/godot_e2e/project.godot`
4. Missing `addons/gecs/` or `addons/gdUnit4/` must not fail existing C#/.NET scaffold.

Then enable the installed plugin entries in `project.godot` and register
`AutomationServer`. C# projects enable only the shared `godot_e2e` plugin here;
GDScript projects enable `gecs`, `gdUnit4`, and `godot_e2e`.

`.godotmaker/config.yaml` is created by `tools/publish.py` before this skill
runs — verify it exists and move on.

### E2E conftest.py template

Write the following to `e2e/conftest.py`:
```python
import os

import pytest
from godot_e2e import GodotE2E

GODOT_PROJECT = os.path.join(os.path.dirname(__file__), "..")
GODOT_CONFIG = os.path.join(GODOT_PROJECT, ".claude", "godotmaker.yaml")


def _read_godot_path():
    try:
        with open(GODOT_CONFIG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if line.startswith("godot_path:"):
                    value = line.split(":", 1)[1].strip().strip("\"'")
                    return value or None
    except OSError:
        return None
    return None


GODOT_PATH = _read_godot_path()

@pytest.fixture(scope="module")
def _game_process():
    with GodotE2E.launch(
        GODOT_PROJECT,
        godot_path=GODOT_PATH,
        timeout=15.0,
    ) as game:
        game.wait_for_node("/root/Main", timeout=10.0)
        yield game

@pytest.fixture(scope="function")
def game(_game_process):
    _game_process.reload_scene()
    _game_process.wait_for_node("/root/Main", timeout=5.0)
    yield _game_process
```

### 3. Initial commit

```bash
git init                              # if not already a git repo
<godot_path> --headless --import      # generate .godot/ cache + *.uid sidecars
git add -A
git commit -m "Scaffold: initial Godot project with addons"
```

Required for `isolation: "worktree"` in worker dispatch — without `HEAD`, parallel workers fail with `fatal: not a valid object name: 'HEAD'`.

### 4. Verify

```bash
python tools/check_project.py <project_dir> --build
```

`--build` is the gm-scaffold readiness check. Shared readiness covers all of:

- `project.godot` exists with `[application]`
- `addons/godot_e2e/` is present with `plugin.cfg`
- no installed addon contains a nested `project.godot`
- `godot-e2e` plugin enabled in `[editor_plugins]`
- `AutomationServer` autoload registered for `godot-e2e`
- `e2e/conftest.py` imports `GodotE2E`
- `.git/` resolves `HEAD` (worker worktree isolation needs it)
- `<godot_path> --headless --quit` exits 0 with no blocking Godot diagnostics

GDScript backend readiness additionally requires:

- `addons/gecs/` and `addons/gdUnit4/` present
- each GDScript-required addon has `plugin.cfg`
- `addons/gdUnit4/bin/GdUnitCmdTool.gd` and
  `addons/gdUnit4/src/core/runners/GdUnitTestCIRunner.gd` exist

Existing C#/.NET backend readiness additionally requires:

- `language_backend: csharp` is recorded or an existing Godot C# `.csproj` / `.sln` is present
- the configured Godot executable reports a Mono/.NET build from `--version`
- Missing `addons/gecs/` or `addons/gdUnit4/` must not fail existing C#/.NET scaffold readiness
- C# unit tests are selected later through `unit_test_backend` / `dotnet_target`, not gdUnit4

The command must exit 0 with no `[FAIL]` entries for scaffold to be
considered done. Shutdown-note `[WARN]` entries do not block scaffold.
If `.claude/godotmaker.yaml` lacks `godot_path`, re-run `tools/publish.py`.

## Available Skills & Tools

| Skill | Purpose |
|-------|---------|
| project-scaffold | Project structure + addon installation |
| godot-api | Godot API reference (sanity-check project.godot syntax) |

## When Done

After verification passes:

1. From the project root run `python tools/append_stage_event.py scaffold` to append a `{"role": "scaffold", "ts": "<server-generated UTC>"}` line to `.godotmaker/stage.jsonl`. Do NOT hand-write the JSON or the timestamp — the helper exists so the timestamp comes from the system clock, not your own output.
2. `git add -A && git commit -m "chore(scaffold): stage event"`
3. Inform the user: `Scaffold complete. Recommended next: /gm-gdd`
