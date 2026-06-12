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

- If `project.godot` exists AND `addons/gecs/` exists AND `git log` has at least one commit → STOP. Tell the user:
  > "Project is already scaffolded. Recommended next: /gm-gdd.
  > If you need to re-scaffold (rare — usually addon migrations are handled by `tools/publish.py`), just tell me."
- Otherwise → proceed.

## Hard Rules

1. **Do NOT design the game here.**
2. **Use fixed 2D defaults.** Use the project-scaffold default viewport (`1280x720`) and rendering method.
3. **Do NOT create Component/System stubs.**
4. **All addons MUST come from `.claude/config/addon_versions.json`** — do not guess versions.
5. **Initial git commit is mandatory and must include import metadata.** Run `<godot_path> --headless --import` before the commit and include generated `.uid` files.

## Scaffold Steps

### 1. Gather minimal inputs

Use `AskUserQuestion` to ask for:
- **Game name** (snake_case, used as project directory name)

Use 2D defaults. GodotMaker currently generates 2D games only; do not ask the
user to choose a dimension during scaffold.

Other settings (genre, art style, mechanics) are deferred to `/gm-gdd`.

### 2a. Run project-scaffold skill

Invoke `.claude/skills/project-scaffold/SKILL.md` with only the gathered game
name. Use project-scaffold defaults for every other template variable. Run only
Steps 1, 2, and 3. Do not run genre adaptations. From Step 3's template table,
fill just these four templates:

- `project.godot.tmpl` → `project.godot`
- `main_scene.tmpl` → `scenes/main.tscn`
- `world_scene.tmpl` → `scenes/game_world.tscn`
- `gitignore.tmpl` → `.gitignore`

That gives you the directory tree, an empty `Main` entry-point scene, the
gameplay scene placeholder, and a sensible `.gitignore`.

The remaining items in project-scaffold belong to other parts of the pipeline:

| project-scaffold concern | Owner |
|--------------------------|-------|
| Component / System / test files (with or without a Game Plan) | decomposer in `/gm-gdd` writes STRUCTURE.md first; workers in `/gm-build` create the actual `.gd` files |
| Genre Adaptations — `[physics]` / `[input]` (Step 4) | `/gm-gdd` |
| Post-Scaffold publish (Step 5) | already done by `tools/publish.py` before scaffold runs |
| Addon install | step 2b below |

### 2b. Install addons and enable godot-e2e plugin

For each entry in `.claude/config/addon_versions.json` matching the chosen
Godot version, clone the repo at the listed tag into the listed `install_path`:

- `addons/gecs/` (csprance/gecs)
- `addons/gdUnit4/` (MikeSchulze/gdUnit4)
- `addons/godot_e2e/` (RandallLiuXin/godot-e2e)

Then enable each addon in `[editor_plugins]` of `project.godot` by
listing its `plugin.cfg` (consult the `plugin: true|false` flag in
`addon_versions.json` — at the time of writing, gecs / gdUnit4 /
godot-e2e are all plugin-enabled).

Ensure `AutomationServer` is registered once in `[autoload]` for
`res://addons/godot_e2e/automation_server.gd`; do not add a second entry
if the template or plugin already registered it.

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

`--build` is the gm-scaffold readiness check — it covers all of:

- `project.godot` exists with `[application]`
- `addons/gecs/`, `addons/gdUnit4/`, `addons/godot_e2e/` present
- `godot-e2e` plugin enabled in `[editor_plugins]`
- `AutomationServer` autoload registered for `godot-e2e`
- `e2e/conftest.py` imports `GodotE2E`
- `.git/` resolves `HEAD` (worker worktree isolation needs it)
- `<godot_path> --headless --quit` exits 0 with no `ERROR` lines
  (godot_path read from `.claude/godotmaker.yaml`, validated at publish time)

All entries must report `[PASS]` for scaffold to be considered done.
If `.claude/godotmaker.yaml` lacks `godot_path` the headless check
emits `[FAIL]` because headless parse is part of the build gate. Re-run
`tools/publish.py` to set the path.

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
